use anyhow::{Context, Result, bail};
use rusqlite::{OptionalExtension, params};

use super::{PendingCheckpointPublication, Store, now_millis, validate_memory_id};

impl Store {
    pub(crate) fn pending_checkpoint_publications(
        &self,
    ) -> Result<Vec<PendingCheckpointPublication>> {
        let raw = {
            let mut statement = self.connection.prepare(
                "SELECT manifest_id,workspace_id,workspace_name,base_memory_ids_json,retained_count \
                 FROM checkpoint_publications WHERE state='pending' ORDER BY created_at",
            )?;
            let rows = statement.query_map([], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, i64>(4)?,
                ))
            })?;
            rows.collect::<rusqlite::Result<Vec<_>>>()?
        };
        raw.into_iter()
            .map(
                |(manifest_id, session_id, session_name, memory_ids, retained_count)| {
                    Ok(PendingCheckpointPublication {
                        manifest_id,
                        session_id,
                        session_name,
                        base_memory_ids: serde_json::from_str(&memory_ids)
                            .context("invalid checkpoint publication memory ids")?,
                        retained_count: usize::try_from(retained_count)?,
                    })
                },
            )
            .collect()
    }

    pub(crate) fn mark_checkpoint_publication_published(
        &self,
        manifest_id: &str,
        memory_id: &str,
    ) -> Result<()> {
        validate_memory_id(memory_id)?;
        let changed = self.connection.execute(
            "UPDATE checkpoint_publications SET state='published',memory_id=?2,published_at=?3 \
             WHERE manifest_id=?1 AND state='pending'",
            params![manifest_id, memory_id, now_millis()],
        )?;
        if changed == 1 {
            return Ok(());
        }
        self.check_completed_publication(manifest_id, memory_id)
    }

    fn check_completed_publication(&self, manifest_id: &str, memory_id: &str) -> Result<()> {
        let existing: Option<(String, Option<String>)> = self
            .connection
            .query_row(
                "SELECT state,memory_id FROM checkpoint_publications WHERE manifest_id=?1",
                [manifest_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        match existing {
            Some((state, Some(existing_id)))
                if state == "published" && existing_id == memory_id =>
            {
                Ok(())
            }
            Some((state, existing_id)) => bail!(
                "checkpoint publication {manifest_id} is {state} with memory id {existing_id:?}"
            ),
            None => bail!("unknown checkpoint publication: {manifest_id}"),
        }
    }
}
