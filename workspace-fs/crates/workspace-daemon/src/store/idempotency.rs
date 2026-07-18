use anyhow::{Result, bail};
use rusqlite::params;

use super::{IdempotencyReservation, Store, now_millis};

impl Store {
    pub(crate) fn reserve_idempotency_request(
        &self,
        key: &str,
        operation: &str,
        request_hash: &str,
    ) -> Result<IdempotencyReservation> {
        let inserted = self.connection.execute(
            "INSERT OR IGNORE INTO idempotency_responses\
             (key,operation,request_hash,response_json,state,created_at) \
             VALUES (?1,?2,?3,'','pending',?4)",
            params![key, operation, request_hash, now_millis()],
        )?;
        if inserted == 1 {
            return Ok(IdempotencyReservation::New);
        }
        self.existing_idempotency_reservation(key)
    }

    pub(crate) fn complete_idempotency_request(
        &self,
        key: &str,
        response_json: &str,
    ) -> Result<()> {
        let changed = self.connection.execute(
            "UPDATE idempotency_responses SET response_json=?2,state='completed' \
             WHERE key=?1 AND state='pending'",
            params![key, response_json],
        )?;
        if changed == 0 {
            bail!("idempotency request is missing or already completed: {key}");
        }
        Ok(())
    }

    fn existing_idempotency_reservation(&self, key: &str) -> Result<IdempotencyReservation> {
        let (operation, request_hash, response, state): (String, Option<String>, String, String) =
            self.connection.query_row(
                "SELECT operation,request_hash,response_json,state \
             FROM idempotency_responses WHERE key=?1",
                [key],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )?;
        let request_hash = request_hash.unwrap_or_default();
        match state.as_str() {
            "completed" => Ok(IdempotencyReservation::Completed {
                operation,
                request_hash,
                response_json: response,
            }),
            "pending" => Ok(IdempotencyReservation::Pending {
                operation,
                request_hash,
            }),
            _ => bail!("invalid persisted idempotency state: {state}"),
        }
    }
}
