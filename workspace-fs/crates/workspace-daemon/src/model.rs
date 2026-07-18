use serde::Serialize;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FileRecord {
    pub path: String,
    pub hash: String,
    pub size: u64,
    pub source_kind: String,
    pub source_ref: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ChangeKind {
    Create,
    Write,
    Delete,
}

impl ChangeKind {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Create => "create",
            Self::Write => "write",
            Self::Delete => "delete",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Change {
    pub path: String,
    pub kind: ChangeKind,
    pub size: Option<u64>,
}

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
    pub state: String,
    pub worktree: String,
    pub head_manifest: Option<String>,
    pub memory_ids: Vec<String>,
    pub changes: Vec<Change>,
}

#[derive(Debug, Serialize)]
pub struct SessionSummary {
    pub session_id: String,
    pub name: String,
    pub state: String,
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
