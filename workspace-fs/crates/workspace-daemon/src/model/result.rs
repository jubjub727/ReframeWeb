use serde::Serialize;

use super::{Change, WorkspaceState};

#[derive(Debug, Serialize)]
pub struct SessionCreated {
    pub session_id: String,
    pub worktree: String,
    pub memory_ids: Vec<String>,
    pub projected_files: usize,
}

#[derive(Debug, Serialize)]
pub struct SessionStatus {
    pub session_id: String,
    pub name: String,
    pub state: WorkspaceState,
    pub worktree: String,
    pub head_manifest: Option<String>,
    pub memory_ids: Vec<String>,
    pub changes: Vec<Change>,
}

#[derive(Debug, Serialize)]
pub struct SessionSummary {
    pub session_id: String,
    pub name: String,
    pub state: WorkspaceState,
    pub head_manifest: Option<String>,
    pub memory_ids: Vec<String>,
    pub created_at: i64,
    pub updated_at: i64,
}

#[derive(Debug, Serialize)]
pub struct CheckpointResult {
    pub session_id: String,
    pub manifest_id: String,
    pub retained_paths: Vec<String>,
    pub remaining_changes: Vec<Change>,
}
