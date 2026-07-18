use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;

use anyhow::{Result, bail};

use crate::model::{BackingBlobLocator, MemoryLocator, RecordSource, SessionCreated, WorkspaceId};
use crate::paths::{ScratchMatcher, scratch_rules};
use crate::store::{PersistedMemorySource, PreparedMemorySource, Store};

use super::scanning::scan_source;
use super::worktree_guard::WorktreeGuard;

#[cfg(test)]
pub fn create(
    store: &mut Store,
    name: &str,
    requested_id: Option<&str>,
    memory_ids: &[String],
    scratch_paths: &[PathBuf],
) -> Result<SessionCreated> {
    let sources = memory_ids
        .iter()
        .map(|id| store.prepare_registered_source(id))
        .collect::<Result<Vec<_>>>()?;
    create_with_sources(store, name, requested_id, &sources, scratch_paths)
}

pub fn create_with_sources(
    store: &mut Store,
    name: &str,
    requested_id: Option<&str>,
    memory_sources: &[PreparedMemorySource],
    scratch_paths: &[PathBuf],
) -> Result<SessionCreated> {
    let id = requested_id
        .map(WorkspaceId::parse)
        .transpose()?
        .unwrap_or_else(WorkspaceId::generate);
    let name = name.trim();
    if name.is_empty() {
        bail!("session name cannot be empty");
    }
    ensure_unique_sources(memory_sources)?;
    store.ensure_workspace_id_available(id.as_str())?;
    let session_root = store.root().join("sessions").join(id.as_str());
    let worktree = session_root.join("worktree");
    if session_root.exists() {
        bail!(
            "session directory already exists: {}",
            session_root.display()
        );
    }
    let scratch_paths = scratch_rules(scratch_paths)?;
    let scratch_matcher = ScratchMatcher::compile(scratch_paths.iter().map(String::as_str))?;
    let baseline = build_baseline(memory_sources, &scratch_matcher)?;

    let worktree_guard = WorktreeGuard::create(&session_root, &worktree)?;
    if let Err(error) = store.create_workspace(
        &id,
        name,
        &worktree,
        memory_sources,
        &scratch_paths,
        &baseline,
    ) {
        return match worktree_guard.cleanup() {
            Ok(()) => Err(error),
            Err(cleanup_error) => Err(error.context(format!(
                "workspace rollback also failed to remove its worktree: {cleanup_error:#}"
            ))),
        };
    }
    worktree_guard.disarm();

    Ok(SessionCreated {
        session_id: id.into_string(),
        worktree: worktree.to_string_lossy().into_owned(),
        memory_ids: memory_sources
            .iter()
            .map(|source| source.id.clone())
            .collect(),
        projected_files: baseline
            .values()
            .filter(|record| record.source.is_projected_file())
            .count(),
    })
}

fn build_baseline(
    memory_sources: &[PreparedMemorySource],
    scratch_matcher: &ScratchMatcher,
) -> Result<BTreeMap<crate::paths::NormalizedPath, crate::model::FileRecord>> {
    let mut baseline = BTreeMap::new();
    for memory in memory_sources {
        match &memory.source {
            PersistedMemorySource::Directory(root) => {
                for mut record in scan_source(root, scratch_matcher)? {
                    if record.source != RecordSource::Directory {
                        record.source = RecordSource::Memory(MemoryLocator {
                            memory_id: memory.id.clone(),
                            relative_path: record.path.clone(),
                        });
                    }
                    baseline.insert(record.path.clone(), record);
                }
            }
            PersistedMemorySource::Checkpoint {
                backing_store,
                manifest_id,
            } => {
                let external = Store::open(backing_store)?;
                for mut record in external
                    .manifest_entries(manifest_id)?
                    .into_iter()
                    .filter(|record| !scratch_matcher.matches(record.path.as_str()))
                {
                    record.source = match record.source {
                        RecordSource::Blob => RecordSource::BackingBlob(BackingBlobLocator {
                            store_root: backing_store.clone(),
                            hash: record.hash.clone(),
                        }),
                        RecordSource::Tombstone => RecordSource::Tombstone,
                        RecordSource::Directory => RecordSource::Directory,
                        ref source => {
                            bail!(
                                "unsupported checkpoint entry source kind: {}",
                                source.kind()
                            )
                        }
                    };
                    baseline.insert(record.path.clone(), record);
                }
            }
        }
    }
    Ok(baseline)
}

fn ensure_unique_sources(memory_sources: &[PreparedMemorySource]) -> Result<()> {
    let mut ids = BTreeSet::new();
    for source in memory_sources {
        if !ids.insert(source.id.as_str()) {
            bail!("memory source is listed more than once: {}", source.id);
        }
    }
    Ok(())
}
