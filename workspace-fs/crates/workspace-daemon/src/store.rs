mod blob_cleanup;
mod blobs;
mod checkpoints;
mod idempotency;
mod journal;
mod memories;
mod migrations;
mod publications;
mod records;
mod retention;
mod transactions;
mod workspaces;

pub(crate) use blobs::VerifiedBlob;

#[cfg(test)]
#[path = "store/memory_tests.rs"]
mod memory_tests;
#[cfg(test)]
mod tests;

use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, bail};
use rusqlite::Connection;

use crate::model::WorkspaceState;

pub(crate) struct WorkspaceStatusRow {
    pub name: String,
    pub state: WorkspaceState,
    pub worktree: PathBuf,
    pub head_manifest: Option<String>,
}

pub(crate) struct WorkspaceSummaryRow {
    pub id: String,
    pub name: String,
    pub state: WorkspaceState,
    pub head_manifest: Option<String>,
    pub created_at: i64,
    pub updated_at: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum IdempotencyReservation {
    New,
    Completed {
        operation: String,
        request_hash: String,
        response_json: String,
    },
    Pending {
        operation: String,
        request_hash: String,
    },
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub(crate) struct PendingCheckpointPublication {
    pub manifest_id: String,
    pub session_id: String,
    pub session_name: String,
    pub base_memory_ids: Vec<String>,
    pub retained_count: usize,
}

pub struct Store {
    root: PathBuf,
    connection: Connection,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PersistedMemorySource {
    Directory(PathBuf),
    Checkpoint {
        backing_store: PathBuf,
        manifest_id: String,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct PreparedMemorySource {
    pub(crate) id: String,
    pub(crate) source: PersistedMemorySource,
}

impl Store {
    pub fn open(root: &Path) -> Result<Self> {
        fs::create_dir_all(root).with_context(|| format!("create store {}", root.display()))?;
        fs::create_dir_all(root.join("blobs"))?;
        fs::create_dir_all(root.join("sessions"))?;
        let mut connection = Connection::open(root.join("workspace.sqlite3"))?;
        connection.pragma_update(None, "journal_mode", "WAL")?;
        connection.pragma_update(None, "foreign_keys", "ON")?;
        migrations::apply(&mut connection)?;
        Ok(Self {
            root: root.to_path_buf(),
            connection,
        })
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    #[cfg(test)]
    pub fn next_id(prefix: &str) -> String {
        format!("{prefix}-{}", uuid::Uuid::new_v4())
    }
}

fn validate_memory_id(id: &str) -> Result<()> {
    if id.is_empty() || id.len() > 256 {
        bail!("resolved memory id must be between 1 and 256 characters");
    }
    Ok(())
}

pub fn now_millis() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as i64
}
