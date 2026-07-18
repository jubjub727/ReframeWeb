use std::collections::BTreeMap;

use anyhow::Result;
use rusqlite::params;

use crate::model::{FileRecord, RecordSource};
use crate::paths::NormalizedPath;

use super::Store;

impl Store {
    pub(crate) fn baseline(
        &self,
        session_id: &str,
    ) -> Result<BTreeMap<NormalizedPath, FileRecord>> {
        self.records(
            "SELECT path,hash,size,source_kind,source_ref FROM baselines \
             WHERE workspace_id=?1 ORDER BY path",
            session_id,
        )
        .map(|records| {
            records
                .into_iter()
                .map(|record| (record.path.clone(), record))
                .collect()
        })
    }

    pub(crate) fn manifest_entries(&self, manifest_id: &str) -> Result<Vec<FileRecord>> {
        self.records(
            "SELECT path,hash,size,source_kind,source_ref FROM manifest_entries \
             WHERE manifest_id=?1 ORDER BY path",
            manifest_id,
        )
    }

    pub(crate) fn manifest_exists(&self, manifest_id: &str) -> Result<bool> {
        self.connection
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM manifests WHERE id=?1)",
                [manifest_id],
                |row| row.get(0),
            )
            .map_err(Into::into)
    }

    fn records(&self, query: &str, key: &str) -> Result<Vec<FileRecord>> {
        let raw = {
            let mut statement = self.connection.prepare(query)?;
            let rows = statement.query_map([key], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, Option<String>>(4)?,
                ))
            })?;
            rows.collect::<rusqlite::Result<Vec<_>>>()?
        };
        raw.into_iter()
            .map(|(path, hash, size, kind, reference)| {
                Ok(FileRecord {
                    path: NormalizedPath::parse_str(&path)?,
                    hash,
                    size: u64::try_from(size)?,
                    source: RecordSource::from_storage(&kind, reference.as_deref())?,
                })
            })
            .collect()
    }
}

pub(super) fn insert_record(
    transaction: &rusqlite::Transaction<'_>,
    query: &str,
    owner_id: &str,
    record: &FileRecord,
) -> Result<()> {
    transaction.execute(
        query,
        params![
            owner_id,
            record.path.as_str(),
            record.hash,
            i64::try_from(record.size)?,
            record.source.kind(),
            record.source.reference_json()?
        ],
    )?;
    Ok(())
}
