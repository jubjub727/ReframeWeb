mod request;

use serde::{Deserialize, Serialize};
use serde_json::Value;

pub use request::Request;

pub const PROTOCOL_VERSION: u32 = 2;
pub const MAX_FRAME_BYTES: usize = 16 * 1024 * 1024;
pub const BUILD_FINGERPRINT: &str = concat!(
    env!("CARGO_PKG_NAME"),
    "@",
    env!("CARGO_PKG_VERSION"),
    "+protocol.2"
);
pub const CAPABILITIES: &[&str] = &[
    "framed-json-v1",
    "idempotent-mutations",
    "idempotency-scopes",
    "operation-metadata",
    "structured-errors",
];

pub mod error_code {
    pub const FRAME_TOO_LARGE: &str = "frame_too_large";
    pub const IDEMPOTENCY_CONFLICT: &str = "idempotency_conflict";
    pub const IDEMPOTENCY_ERROR: &str = "idempotency_error";
    pub const IDEMPOTENCY_REQUIRED: &str = "idempotency_required";
    pub const INVALID_JSON: &str = "invalid_json";
    pub const INVALID_REQUEST: &str = "invalid_request";
    pub const OPERATION_FAILED: &str = "operation_failed";
    pub const OUTCOME_UNKNOWN: &str = "outcome_unknown";
    pub const RESPONSE_TOO_LARGE: &str = "response_too_large";
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "operation", rename_all = "snake_case", deny_unknown_fields)]
pub enum Operation {
    Hello {},
    Health {},
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
    ListPendingCheckpointPublications {},
    CompleteCheckpointPublication {
        manifest_id: String,
        memory_id: String,
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
    Shutdown {},
}

impl Operation {
    pub fn name(&self) -> &'static str {
        self.metadata().name
    }

    pub fn mutates(&self) -> bool {
        self.metadata().mutates
    }

    pub fn idempotency_scope(&self) -> IdempotencyScope {
        self.metadata().idempotency_scope
    }

    pub fn metadata(&self) -> &'static OperationMetadata {
        match self {
            Self::Hello {} => &HELLO_METADATA,
            Self::Health {} => &HEALTH_METADATA,
            Self::CreateWorkspace { .. } => &CREATE_WORKSPACE_METADATA,
            Self::ApplyPolicy { .. } => &APPLY_POLICY_METADATA,
            Self::MountWorkspace { .. } => &MOUNT_WORKSPACE_METADATA,
            Self::Prefetch { .. } => &PREFETCH_METADATA,
            Self::GetChangeJournal { .. } => &GET_CHANGE_JOURNAL_METADATA,
            Self::GetWorkspaceStatus { .. } => &GET_WORKSPACE_STATUS_METADATA,
            Self::ListWorkspaces { .. } => &LIST_WORKSPACES_METADATA,
            Self::ReadFileSummary { .. } => &READ_FILE_SUMMARY_METADATA,
            Self::CommitCheckpoint { .. } => &COMMIT_CHECKPOINT_METADATA,
            Self::ListPendingCheckpointPublications {} => {
                &LIST_PENDING_CHECKPOINT_PUBLICATIONS_METADATA
            }
            Self::CompleteCheckpointPublication { .. } => &COMPLETE_CHECKPOINT_PUBLICATION_METADATA,
            Self::UnmountWorkspace { .. } => &UNMOUNT_WORKSPACE_METADATA,
            Self::CloseWorkspace { .. } => &CLOSE_WORKSPACE_METADATA,
            Self::DestroyEphemeralWorkspace { .. } => &DESTROY_EPHEMERAL_WORKSPACE_METADATA,
            Self::Shutdown {} => &SHUTDOWN_METADATA,
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize)]
pub struct OperationMetadata {
    pub name: &'static str,
    pub mutates: bool,
    pub idempotency_scope: IdempotencyScope,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum IdempotencyScope {
    None,
    Durable,
    ProcessLocal,
}

macro_rules! operation_metadata {
    ($constant:ident, $name:literal, $mutates:literal, $scope:ident) => {
        const $constant: OperationMetadata = OperationMetadata {
            name: $name,
            mutates: $mutates,
            idempotency_scope: IdempotencyScope::$scope,
        };
    };
}

operation_metadata!(HELLO_METADATA, "hello", false, None);
operation_metadata!(HEALTH_METADATA, "health", false, None);
operation_metadata!(CREATE_WORKSPACE_METADATA, "create_workspace", true, Durable);
operation_metadata!(APPLY_POLICY_METADATA, "apply_policy", true, Durable);
operation_metadata!(
    MOUNT_WORKSPACE_METADATA,
    "mount_workspace",
    true,
    ProcessLocal
);
operation_metadata!(PREFETCH_METADATA, "prefetch", true, ProcessLocal);
operation_metadata!(
    GET_CHANGE_JOURNAL_METADATA,
    "get_change_journal",
    false,
    None
);
operation_metadata!(
    GET_WORKSPACE_STATUS_METADATA,
    "get_workspace_status",
    false,
    None
);
operation_metadata!(LIST_WORKSPACES_METADATA, "list_workspaces", false, None);
operation_metadata!(READ_FILE_SUMMARY_METADATA, "read_file_summary", false, None);
operation_metadata!(
    COMMIT_CHECKPOINT_METADATA,
    "commit_checkpoint",
    true,
    Durable
);
operation_metadata!(
    LIST_PENDING_CHECKPOINT_PUBLICATIONS_METADATA,
    "list_pending_checkpoint_publications",
    false,
    None
);
operation_metadata!(
    COMPLETE_CHECKPOINT_PUBLICATION_METADATA,
    "complete_checkpoint_publication",
    true,
    Durable
);
operation_metadata!(
    UNMOUNT_WORKSPACE_METADATA,
    "unmount_workspace",
    true,
    ProcessLocal
);
operation_metadata!(CLOSE_WORKSPACE_METADATA, "close_workspace", true, Durable);
operation_metadata!(
    DESTROY_EPHEMERAL_WORKSPACE_METADATA,
    "destroy_ephemeral_workspace",
    true,
    Durable
);
operation_metadata!(SHUTDOWN_METADATA, "shutdown", true, ProcessLocal);

pub const OPERATIONS: &[OperationMetadata] = &[
    HELLO_METADATA,
    HEALTH_METADATA,
    CREATE_WORKSPACE_METADATA,
    APPLY_POLICY_METADATA,
    MOUNT_WORKSPACE_METADATA,
    PREFETCH_METADATA,
    GET_CHANGE_JOURNAL_METADATA,
    GET_WORKSPACE_STATUS_METADATA,
    LIST_WORKSPACES_METADATA,
    READ_FILE_SUMMARY_METADATA,
    COMMIT_CHECKPOINT_METADATA,
    LIST_PENDING_CHECKPOINT_PUBLICATIONS_METADATA,
    COMPLETE_CHECKPOINT_PUBLICATION_METADATA,
    UNMOUNT_WORKSPACE_METADATA,
    CLOSE_WORKSPACE_METADATA,
    DESTROY_EPHEMERAL_WORKSPACE_METADATA,
    SHUTDOWN_METADATA,
];

#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "source_kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum MemorySourceDto {
    Directory {
        memory_id: String,
        source_path: String,
    },
    Checkpoint {
        memory_id: String,
        backing_store: String,
        manifest_id: String,
    },
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
