use std::collections::BTreeMap;
use std::path::Path;

use anyhow::{Context, Result, bail};
use rusqlite::params;

use crate::model::{Change, FileRecord, WorkspaceId, WorkspaceState};
use crate::paths::NormalizedPath;

use super::memories::insert_or_compare_memory;
use super::records::insert_record;
use super::{PreparedMemorySource, Store, now_millis};

impl Store {
    pub(crate) fn create_workspace(
        &mut self,
        id: &WorkspaceId,
        name: &str,
        worktree: &Path,
        memory_sources: &[PreparedMemorySource],
        scratch_paths: &[String],
        baseline: &BTreeMap<NormalizedPath, FileRecord>,
    ) -> Result<()> {
        let now = now_millis();
        let transaction = self.connection.transaction()?;
        for source in memory_sources {
            insert_or_compare_memory(&transaction, source)?;
        }
        transaction.execute(
            "INSERT INTO workspaces(id,name,state,worktree_path,head_manifest,created_at,updated_at)\
             VALUES (?1,?2,'active',?3,?4,?5,?5)",
            params![
                id.as_str(),
                name,
                worktree.to_string_lossy(),
                Option::<String>::None,
                now
            ],
        )?;
        for (ordinal, source) in memory_sources.iter().enumerate() {
            transaction.execute(
                "INSERT INTO workspace_sources(workspace_id,memory_id,ordinal) VALUES (?1,?2,?3)",
                params![id.as_str(), source.id, i64::try_from(ordinal)?],
            )?;
        }
        for path in scratch_paths {
            transaction.execute(
                "INSERT INTO workspace_scratch(workspace_id,path) VALUES (?1,?2)",
                params![id.as_str(), path],
            )?;
        }
        for record in baseline.values() {
            insert_record(
                &transaction,
                "INSERT INTO baselines(workspace_id,path,hash,size,source_kind,source_ref) \
                 VALUES (?1,?2,?3,?4,?5,?6)",
                id.as_str(),
                record,
            )?;
        }
        transaction.commit()?;
        Ok(())
    }

    pub(crate) fn replace_scratch_paths(
        &mut self,
        session_id: &str,
        paths: &[String],
    ) -> Result<()> {
        let transaction = self.connection.transaction()?;
        let state: String = transaction
            .query_row(
                "SELECT state FROM workspaces WHERE id=?1",
                [session_id],
                |row| row.get(0),
            )
            .with_context(|| format!("unknown session: {session_id}"))?;
        if WorkspaceState::parse(&state)? != WorkspaceState::Active {
            bail!("cannot change policy for a closed session");
        }
        transaction.execute(
            "DELETE FROM workspace_scratch WHERE workspace_id=?1",
            [session_id],
        )?;
        for path in paths {
            transaction.execute(
                "INSERT INTO workspace_scratch(workspace_id,path) VALUES (?1,?2)",
                params![session_id, path],
            )?;
        }
        transaction.commit()?;
        Ok(())
    }

    pub(crate) fn replace_journal(&mut self, session_id: &str, changes: &[Change]) -> Result<()> {
        let transaction = self.connection.transaction()?;
        transaction.execute(
            "DELETE FROM journal_events WHERE workspace_id=?1",
            [session_id],
        )?;
        let scanned_at = now_millis();
        for change in changes {
            transaction.execute(
                "INSERT INTO journal_events(workspace_id,path,kind,size,scanned_at) \
                 VALUES (?1,?2,?3,?4,?5)",
                params![
                    session_id,
                    change.path,
                    change.kind.as_str(),
                    change.size.map(i64::try_from).transpose()?,
                    scanned_at
                ],
            )?;
        }
        transaction.commit()?;
        Ok(())
    }
}
