use crate::model::{Change, ChangeKind};
use crate::paths::NormalizedPath;
use anyhow::Result;

use super::Store;

impl Store {
    pub(crate) fn journal(&self, session_id: &str) -> Result<Vec<Change>> {
        let raw = {
            let mut statement = self.connection.prepare(
                "SELECT path,kind,size FROM journal_events WHERE workspace_id=?1 ORDER BY path",
            )?;
            let rows = statement.query_map([session_id], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, Option<i64>>(2)?,
                ))
            })?;
            rows.collect::<rusqlite::Result<Vec<_>>>()?
        };
        raw.into_iter()
            .map(|(path, kind, size)| {
                Ok(Change {
                    path: NormalizedPath::parse_str(&path)?.into_string(),
                    kind: ChangeKind::parse(&kind)?,
                    size: size.map(u64::try_from).transpose()?,
                })
            })
            .collect()
    }
}
