use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Deserialize)]
pub struct Request {
    pub request_id: String,
    pub idempotency_key: Option<String>,
    #[serde(flatten)]
    pub operation: Operation,
}

#[derive(Debug, Deserialize)]
#[serde(tag = "operation", rename_all = "snake_case")]
pub enum Operation {
    Hello,
    Health,
    CreateWorkspace {
        name: String,
        session_id: Option<String>,
        #[serde(default)]
        memory_sources: Vec<MemorySourceDto>,
        #[serde(default)]
        scratch_paths: Vec<String>,
    },
    ApplyPolicy {
        session_id: String,
        #[serde(default)]
        scratch_paths: Vec<String>,
    },
    MountWorkspace {
        session_id: String,
    },
    Prefetch {
        session_id: String,
        paths: Vec<String>,
    },
    GetChangeJournal {
        session_id: String,
    },
    GetWorkspaceStatus {
        session_id: String,
    },
    ListWorkspaces {
        #[serde(default)]
        active_only: bool,
    },
    ReadFileSummary {
        session_id: String,
        path: String,
        max_bytes: Option<usize>,
    },
    CommitCheckpoint {
        session_id: String,
        #[serde(default)]
        paths: Vec<String>,
        #[serde(default)]
        all: bool,
    },
    UnmountWorkspace {
        session_id: String,
    },
    CloseWorkspace {
        session_id: String,
    },
    DestroyEphemeralWorkspace {
        session_id: String,
    },
    Shutdown,
}

impl Operation {
    pub fn name(&self) -> &'static str {
        match self {
            Self::Hello => "hello",
            Self::Health => "health",
            Self::CreateWorkspace { .. } => "create_workspace",
            Self::ApplyPolicy { .. } => "apply_policy",
            Self::MountWorkspace { .. } => "mount_workspace",
            Self::Prefetch { .. } => "prefetch",
            Self::GetChangeJournal { .. } => "get_change_journal",
            Self::GetWorkspaceStatus { .. } => "get_workspace_status",
            Self::ListWorkspaces { .. } => "list_workspaces",
            Self::ReadFileSummary { .. } => "read_file_summary",
            Self::CommitCheckpoint { .. } => "commit_checkpoint",
            Self::UnmountWorkspace { .. } => "unmount_workspace",
            Self::CloseWorkspace { .. } => "close_workspace",
            Self::DestroyEphemeralWorkspace { .. } => "destroy_ephemeral_workspace",
            Self::Shutdown => "shutdown",
        }
    }

    pub fn mutates(&self) -> bool {
        !matches!(
            self,
            Self::Hello
                | Self::Health
                | Self::GetChangeJournal { .. }
                | Self::GetWorkspaceStatus { .. }
                | Self::ListWorkspaces { .. }
                | Self::ReadFileSummary { .. }
        )
    }
}

#[derive(Debug, Deserialize)]
pub struct MemorySourceDto {
    pub memory_id: String,
    pub source_kind: String,
    pub source_path: Option<String>,
    pub backing_store: Option<String>,
    pub manifest_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Response {
    pub request_id: String,
    pub ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<ProtocolError>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProtocolError {
    pub code: String,
    pub operation: String,
    pub workspace_id: Option<String>,
    pub message: String,
}
