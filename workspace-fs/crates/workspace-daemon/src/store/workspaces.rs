use std::path::PathBuf;

use anyhow::{Context, Result, bail};
use rusqlite::{OptionalExtension, params};

use crate::model::WorkspaceState;

use super::{Store, WorkspaceStatusRow, WorkspaceSummaryRow, now_millis};

impl Store {
    pub(crate) fn ensure_workspace_id_available(&self, session_id: &str) -> Result<()> {
        let existing = self
            .connection
            .query_row(
                "SELECT id FROM workspaces WHERE id=?1",
                [session_id],
                |row| row.get::<_, String>(0),
            )
            .optional()?;
        if existing.is_some() {
            bail!("session already exists: {session_id}");
        }
        Ok(())
    }

    pub(crate) fn workspace_status(&self, session_id: &str) -> Result<WorkspaceStatusRow> {
        let (name, state, worktree, head_manifest): (String, String, String, Option<String>) = self
            .connection
            .query_row(
                "SELECT name,state,worktree_path,head_manifest FROM workspaces WHERE id=?1",
                [session_id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .with_context(|| format!("unknown session: {session_id}"))?;
        Ok(WorkspaceStatusRow {
            name,
            state: WorkspaceState::parse(&state)?,
            worktree: PathBuf::from(worktree),
            head_manifest,
        })
    }

    pub(crate) fn worktree(&self, session_id: &str) -> Result<PathBuf> {
        self.workspace_status(session_id).map(|row| row.worktree)
    }

    pub(crate) fn ensure_active(&self, session_id: &str) -> Result<()> {
        if self.workspace_status(session_id)?.state != WorkspaceState::Active {
            bail!("workspace is closed: {session_id}");
        }
        Ok(())
    }

    pub(crate) fn close_workspace(&self, session_id: &str) -> Result<()> {
        let changed = self.connection.execute(
            "UPDATE workspaces SET state='closed',updated_at=?2 WHERE id=?1",
            params![session_id, now_millis()],
        )?;
        if changed == 0 {
            bail!("unknown session: {session_id}");
        }
        Ok(())
    }

    pub(crate) fn scratch_paths(&self, session_id: &str) -> Result<Vec<String>> {
        let mut statement = self
            .connection
            .prepare("SELECT path FROM workspace_scratch WHERE workspace_id=?1 ORDER BY path")?;
        let rows = statement.query_map([session_id], |row| row.get(0))?;
        rows.collect::<rusqlite::Result<Vec<_>>>()
            .map_err(Into::into)
    }

    pub(crate) fn memory_ids(&self, session_id: &str) -> Result<Vec<String>> {
        let mut statement = self.connection.prepare(
            "SELECT memory_id FROM workspace_sources WHERE workspace_id=?1 ORDER BY ordinal",
        )?;
        let rows = statement.query_map([session_id], |row| row.get(0))?;
        rows.collect::<rusqlite::Result<Vec<_>>>()
            .map_err(Into::into)
    }

    pub(crate) fn workspace_summaries(
        &self,
        active_only: bool,
    ) -> Result<Vec<WorkspaceSummaryRow>> {
        let query = if active_only {
            "SELECT id,name,state,head_manifest,created_at,updated_at FROM workspaces \
             WHERE state='active' ORDER BY created_at DESC,rowid DESC"
        } else {
            "SELECT id,name,state,head_manifest,created_at,updated_at FROM workspaces \
             ORDER BY created_at DESC,rowid DESC"
        };
        let raw = {
            let mut statement = self.connection.prepare(query)?;
            let rows = statement.query_map([], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, Option<String>>(3)?,
                    row.get::<_, i64>(4)?,
                    row.get::<_, i64>(5)?,
                ))
            })?;
            rows.collect::<rusqlite::Result<Vec<_>>>()?
        };
        raw.into_iter()
            .map(|(id, name, state, head_manifest, created_at, updated_at)| {
                Ok(WorkspaceSummaryRow {
                    id,
                    name,
                    state: WorkspaceState::parse(&state)?,
                    head_manifest,
                    created_at,
                    updated_at,
                })
            })
            .collect()
    }

    pub(crate) fn head_manifest(&self, session_id: &str) -> Result<Option<String>> {
        self.connection
            .query_row(
                "SELECT head_manifest FROM workspaces WHERE id=?1",
                [session_id],
                |row| row.get(0),
            )
            .with_context(|| format!("unknown session: {session_id}"))
    }
}
