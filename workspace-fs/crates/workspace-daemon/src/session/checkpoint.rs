use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Result, bail};

use crate::model::{ChangeKind, CheckpointResult, FileRecord, ManifestId, RecordSource};
use crate::paths::{NormalizedPath, native_path};
use crate::resident::ResidentWorkspace;
use crate::store::Store;

use super::state::{journal, manifest_entries, scratch_matcher, worktree};

pub fn checkpoint(
    store: &mut Store,
    session_id: &str,
    includes: &[PathBuf],
    all: bool,
) -> Result<CheckpointResult> {
    checkpoint_with_reader(
        store,
        session_id,
        includes,
        all,
        |store, worktree, path| {
            let bytes = fs::read(native_path(worktree, path))?;
            let size = bytes.len() as u64;
            Ok((store.put_blob(&bytes)?, size))
        },
        |worktree, path| native_path(worktree, path).is_dir(),
    )
}

pub fn checkpoint_resident(
    store: &mut Store,
    session_id: &str,
    includes: &[PathBuf],
    all: bool,
    resident: &ResidentWorkspace,
) -> Result<CheckpointResult> {
    checkpoint_with_reader(
        store,
        session_id,
        includes,
        all,
        |store, _worktree, path| {
            let file = resident
                .file(path.as_str())
                .ok_or_else(|| anyhow::anyhow!("resident checkpoint file is missing: {path}"))?;
            let blob = file.verified_blob()?;
            Ok((store.put_verified_blob(&blob)?, blob.bytes().len() as u64))
        },
        |_worktree, path| resident.is_directory(path.as_str()),
    )
}

fn checkpoint_with_reader(
    store: &mut Store,
    session_id: &str,
    includes: &[PathBuf],
    all: bool,
    persist_file: impl Fn(&Store, &Path, &NormalizedPath) -> Result<(String, u64)>,
    is_directory: impl Fn(&Path, &NormalizedPath) -> bool,
) -> Result<CheckpointResult> {
    let changes = journal(store, session_id)?;
    let scratch = scratch_matcher(store, session_id)?;
    if !all && includes.is_empty() {
        bail!("checkpoint defaults to discard; pass --include PATH or --all");
    }
    let selected = if all {
        changes
            .iter()
            .map(|change| NormalizedPath::parse_str(&change.path))
            .collect::<Result<BTreeSet<_>>>()?
    } else {
        includes
            .iter()
            .map(|path| NormalizedPath::parse(path))
            .collect::<Result<BTreeSet<_>>>()?
    };
    let changed: BTreeSet<_> = changes.iter().map(|change| change.path.as_str()).collect();
    for path in &selected {
        if !changed.contains(path.as_str()) {
            bail!("checkpoint path is not changed: {path}");
        }
        if scratch.matches(path.as_str()) {
            bail!("scratch paths can never be checkpointed: {path}");
        }
    }

    let worktree = worktree(store, session_id)?;
    let parent = store.head_manifest(session_id)?;
    let mut retained = retained_parent(store, parent.as_deref())?;
    apply_selected_changes(
        store,
        &worktree,
        &changes,
        &selected,
        &mut retained,
        &persist_file,
        &is_directory,
    )?;

    let manifest_id = ManifestId::generate();
    store.commit_checkpoint(
        session_id,
        &manifest_id,
        parent.as_deref(),
        &retained,
        &selected,
    )?;
    let remaining_changes = journal(store, session_id)?;
    Ok(CheckpointResult {
        session_id: session_id.into(),
        manifest_id: manifest_id.into_string(),
        retained_paths: selected
            .into_iter()
            .map(NormalizedPath::into_string)
            .collect(),
        remaining_changes,
    })
}

fn retained_parent(
    store: &Store,
    parent: Option<&str>,
) -> Result<BTreeMap<NormalizedPath, FileRecord>> {
    match parent {
        Some(parent) => Ok(manifest_entries(store, parent)?
            .into_iter()
            .map(|record| (record.path.clone(), record))
            .collect()),
        None => Ok(BTreeMap::new()),
    }
}

fn apply_selected_changes(
    store: &Store,
    worktree: &Path,
    changes: &[crate::model::Change],
    selected: &BTreeSet<NormalizedPath>,
    retained: &mut BTreeMap<NormalizedPath, FileRecord>,
    persist_file: &impl Fn(&Store, &Path, &NormalizedPath) -> Result<(String, u64)>,
    is_directory: &impl Fn(&Path, &NormalizedPath) -> bool,
) -> Result<()> {
    for change in changes {
        let path = NormalizedPath::parse_str(&change.path)?;
        if !selected.contains(path.as_str()) {
            continue;
        }
        match change.kind {
            ChangeKind::Delete => {
                retained.insert(
                    path.clone(),
                    FileRecord {
                        path,
                        hash: String::new(),
                        size: 0,
                        source: RecordSource::Tombstone,
                    },
                );
            }
            ChangeKind::Create | ChangeKind::Write if is_directory(worktree, &path) => {
                retained.insert(
                    path.clone(),
                    FileRecord {
                        path,
                        hash: String::new(),
                        size: 0,
                        source: RecordSource::Directory,
                    },
                );
            }
            ChangeKind::Create | ChangeKind::Write => {
                let (hash, size) = persist_file(store, worktree, &path)?;
                retained.insert(
                    path.clone(),
                    FileRecord {
                        path,
                        hash,
                        size,
                        source: RecordSource::Blob,
                    },
                );
            }
        }
    }
    Ok(())
}
