use std::collections::BTreeMap;
use std::path::PathBuf;

use anyhow::Result;

use crate::model::{Change, FileRecord, SessionSummary};
use crate::paths::{NormalizedPath, ScratchMatcher};
use crate::store::Store;

pub fn worktree(store: &Store, session_id: &str) -> Result<PathBuf> {
    store.worktree(session_id)
}

fn scratch_paths(store: &Store, session_id: &str) -> Result<Vec<String>> {
    store.scratch_paths(session_id)
}

pub fn ensure_active(store: &Store, session_id: &str) -> Result<()> {
    store.ensure_active(session_id)
}

pub fn scratch_matcher(store: &Store, session_id: &str) -> Result<ScratchMatcher> {
    let paths = scratch_paths(store, session_id)?;
    ScratchMatcher::compile(paths.iter().map(String::as_str))
}

pub fn list(store: &Store, active_only: bool) -> Result<Vec<SessionSummary>> {
    store
        .workspace_summaries(active_only)?
        .into_iter()
        .map(|row| {
            Ok(SessionSummary {
                memory_ids: store.memory_ids(&row.id)?,
                session_id: row.id,
                name: row.name,
                state: row.state,
                head_manifest: row.head_manifest,
                created_at: row.created_at,
                updated_at: row.updated_at,
            })
        })
        .collect()
}

pub fn baseline(store: &Store, session_id: &str) -> Result<BTreeMap<NormalizedPath, FileRecord>> {
    store.baseline(session_id)
}

pub(super) fn manifest_entries(store: &Store, manifest: &str) -> Result<Vec<FileRecord>> {
    store.manifest_entries(manifest)
}

pub(super) fn memory_ids(store: &Store, session_id: &str) -> Result<Vec<String>> {
    store.memory_ids(session_id)
}

pub(super) fn journal(store: &Store, session_id: &str) -> Result<Vec<Change>> {
    store.journal(session_id)
}

pub fn replace_journal(store: &mut Store, session_id: &str, changes: &[Change]) -> Result<()> {
    store.replace_journal(session_id, changes)
}
