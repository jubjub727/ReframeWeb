use anyhow::Result;
use rusqlite::params;

use super::{Store, now_millis};

const TERMINAL_PROTOCOL_RETENTION_MILLIS: i64 = 30 * 24 * 60 * 60 * 1_000;

impl Store {
    pub(crate) fn prune_protocol_history(&mut self) -> Result<()> {
        self.prune_protocol_history_before(
            now_millis().saturating_sub(TERMINAL_PROTOCOL_RETENTION_MILLIS),
        )
    }

    pub(crate) fn prune_protocol_history_before(&mut self, cutoff: i64) -> Result<()> {
        let transaction = self.connection.transaction()?;
        transaction.execute(
            "DELETE FROM idempotency_responses WHERE state='completed' AND created_at < ?1",
            params![cutoff],
        )?;
        transaction.execute(
            "DELETE FROM checkpoint_publications \
             WHERE state='published' AND published_at < ?1",
            params![cutoff],
        )?;
        transaction.commit()?;
        Ok(())
    }
}
