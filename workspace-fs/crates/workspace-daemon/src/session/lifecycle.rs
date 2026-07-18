use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::PathBuf;

use anyhow::{Context, Result, bail};

use crate::model::{Change, ChangeKind, RecordSource, SessionStatus};
use crate::paths::{NormalizedPath, scratch_rules};
use crate::store::Store;

use super::scanning::{baseline_path_deleted, scan_worktree};
use super::state::{baseline, journal, memory_ids, replace_journal, scratch_matcher, worktree};

pub fn status(store: &mut Store, session_id: &str, refresh: bool) -> Result<SessionStatus> {
    if refresh {
        scan_changes(store, session_id)?;
    }
    let row = store.workspace_status(session_id)?;
    Ok(SessionStatus {
        session_id: session_id.into(),
        name: row.name,
        state: row.state,
        worktree: row.worktree.to_string_lossy().into_owned(),
        head_manifest: row.head_manifest,
        memory_ids: memory_ids(store, session_id)?,
        changes: journal(store, session_id)?,
    })
}

pub fn scan_changes(store: &mut Store, session_id: &str) -> Result<Vec<Change>> {
    let worktree = worktree(store, session_id)?;
    let baseline = baseline(store, session_id)?;
    let scratch = scratch_matcher(store, session_id)?;
    let known_deleted = journal(store, session_id)?
        .into_iter()
        .filter(|change| change.kind == ChangeKind::Delete)
        .map(|change| NormalizedPath::parse_str(&change.path))
        .collect::<Result<BTreeSet<_>>>()?;
    let current: BTreeMap<_, _> = scan_worktree(&worktree, &baseline, &scratch)?
        .into_iter()
        .filter(|record| !scratch.matches(record.path.as_str()))
        .map(|record| (record.path.clone(), record))
        .collect();
    let mut changes = Vec::new();
    for (path, record) in &current {
        match baseline.get(path.as_str()) {
            None => changes.push(Change {
                path: path.to_string(),
                kind: ChangeKind::Create,
                size: Some(record.size),
            }),
            Some(old) if old.hash != record.hash => changes.push(Change {
                path: path.to_string(),
                kind: ChangeKind::Write,
                size: Some(record.size),
            }),
            _ => {}
        }
    }
    for (path, old) in &baseline {
        if old.source != RecordSource::Tombstone
            && !current.contains_key(path.as_str())
            && (known_deleted.contains(path.as_str()) || baseline_path_deleted(&worktree, path))
        {
            changes.push(Change {
                path: path.to_string(),
                kind: ChangeKind::Delete,
                size: None,
            });
        }
    }
    changes.sort_by(|left, right| left.path.cmp(&right.path));
    replace_journal(store, session_id, &changes)?;
    Ok(changes)
}

pub fn close(store: &Store, session_id: &str) -> Result<()> {
    store.close_workspace(session_id)
}

pub fn apply_scratch_paths(store: &mut Store, session_id: &str, paths: &[PathBuf]) -> Result<()> {
    let normalized = scratch_rules(paths)?;
    store.replace_scratch_paths(session_id, &normalized)
}

pub fn destroy_ephemeral(store: &Store, session_id: &str) -> Result<()> {
    let worktree = worktree(store, session_id)?;
    let sessions_root = store.root().join("sessions").canonicalize()?;
    let session_root = worktree
        .parent()
        .context("session worktree has no parent")?;
    let canonical_parent = session_root
        .parent()
        .context("session root has no parent")?
        .canonicalize()?;
    if canonical_parent != sessions_root {
        bail!("refusing to remove a path outside the session store");
    }
    // Persist the recoverable state transition before touching the worktree. If
    // removal fails, a later destroy call can safely retry against the closed
    // session instead of leaving an active row pointing at missing files.
    close(store, session_id)?;
    if session_root.exists() {
        fs::remove_dir_all(session_root)?;
    }
    Ok(())
}
