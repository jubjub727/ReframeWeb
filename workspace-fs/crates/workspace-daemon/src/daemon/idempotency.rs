impl Daemon {
    fn cached_response(&self, key: &str, operation: &str) -> Result<Option<Response>> {
        let row: Option<(String, String)> = self
            .store
            .connection()
            .query_row(
                "SELECT operation,response_json FROM idempotency_responses WHERE key=?1",
                [key],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        let Some((stored_operation, response)) = row else {
            return Ok(None);
        };
        if stored_operation != operation {
            bail!("idempotency key was already used for {stored_operation}");
        }
        Ok(Some(serde_json::from_str(&response)?))
    }

    fn cache_response(&self, key: &str, operation: &str, response: &Response) -> Result<()> {
        self.store.connection().execute(
            "INSERT OR IGNORE INTO idempotency_responses(key,operation,response_json,created_at) VALUES (?1,?2,?3,?4)",
            params![key, operation, serde_json::to_string(response)?, now_millis()],
        )?;
        Ok(())
    }
}
