use std::collections::{BTreeMap, BTreeSet};

use anyhow::Result;
use rusqlite::params;

use crate::model::{FileRecord, ManifestId};
use crate::paths::NormalizedPath;

use super::records::insert_record;
use super::{Store, now_millis};

impl Store {
    pub(crate) fn commit_checkpoint(
        &mut self,
        session_id: &str,
        manifest_id: &ManifestId,
        parent: Option<&str>,
        retained: &BTreeMap<NormalizedPath, FileRecord>,
        selected: &BTreeSet<NormalizedPath>,
    ) -> Result<()> {
        let now = now_millis();
        let transaction = self.connection.transaction()?;
        transaction.execute(
            "INSERT INTO manifests(id,workspace_id,parent_id,created_at) VALUES (?1,?2,?3,?4)",
            params![manifest_id.as_str(), session_id, parent, now],
        )?;
        for record in retained.values() {
            insert_record(
                &transaction,
                "INSERT INTO manifest_entries(manifest_id,path,hash,size,source_kind,source_ref) \
                 VALUES (?1,?2,?3,?4,?5,?6)",
                manifest_id.as_str(),
                record,
            )?;
        }
        transaction.execute(
            "UPDATE workspaces SET head_manifest=?2,updated_at=?3 WHERE id=?1",
            params![session_id, manifest_id.as_str(), now],
        )?;
        for path in selected {
            update_baseline(&transaction, session_id, path, retained.get(path.as_str()))?;
            transaction.execute(
                "DELETE FROM journal_events WHERE workspace_id=?1 AND path=?2",
                params![session_id, path.as_str()],
            )?;
        }
        insert_publication_outbox(
            &transaction,
            session_id,
            manifest_id.as_str(),
            selected.len(),
            now,
        )?;
        transaction.commit()?;
        Ok(())
    }
}

fn update_baseline(
    transaction: &rusqlite::Transaction<'_>,
    session_id: &str,
    path: &NormalizedPath,
    record: Option<&FileRecord>,
) -> Result<()> {
    if let Some(record) = record {
        transaction.execute(
            "INSERT INTO baselines(workspace_id,path,hash,size,source_kind,source_ref) \
             VALUES (?1,?2,?3,?4,?5,?6) ON CONFLICT(workspace_id,path) DO UPDATE SET \
             hash=excluded.hash,size=excluded.size,source_kind=excluded.source_kind,\
             source_ref=excluded.source_ref",
            params![
                session_id,
                path.as_str(),
                record.hash,
                i64::try_from(record.size)?,
                record.source.kind(),
                record.source.reference_json()?
            ],
        )?;
    } else {
        transaction.execute(
            "DELETE FROM baselines WHERE workspace_id=?1 AND path=?2",
            params![session_id, path.as_str()],
        )?;
    }
    Ok(())
}

fn insert_publication_outbox(
    transaction: &rusqlite::Transaction<'_>,
    session_id: &str,
    manifest_id: &str,
    retained_count: usize,
    created_at: i64,
) -> Result<()> {
    let session_name: String = transaction.query_row(
        "SELECT name FROM workspaces WHERE id=?1",
        [session_id],
        |row| row.get(0),
    )?;
    let memory_ids = {
        let mut statement = transaction.prepare(
            "SELECT memory_id FROM workspace_sources WHERE workspace_id=?1 ORDER BY ordinal",
        )?;
        let rows = statement.query_map([session_id], |row| row.get::<_, String>(0))?;
        rows.collect::<rusqlite::Result<Vec<_>>>()?
    };
    transaction.execute(
        "INSERT INTO checkpoint_publications(\
         manifest_id,workspace_id,workspace_name,base_memory_ids_json,retained_count,\
         state,memory_id,created_at,published_at) \
         VALUES (?1,?2,?3,?4,?5,'pending',NULL,?6,NULL)",
        params![
            manifest_id,
            session_id,
            session_name,
            serde_json::to_string(&memory_ids)?,
            i64::try_from(retained_count)?,
            created_at
        ],
    )?;
    Ok(())
}
