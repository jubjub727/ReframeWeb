use anyhow::{Context, Result, bail};
use rusqlite::{Connection, OptionalExtension, params};

use super::super::{PersistedMemorySource, PreparedMemorySource, now_millis};

type MemoryIdentity = (String, String, Option<String>);

pub(super) fn ensure_available(
    connection: &Connection,
    prepared: &PreparedMemorySource,
) -> Result<()> {
    if let Some(existing) = memory_identity(connection, &prepared.id)? {
        ensure_same(&prepared.id, &existing, &identity(prepared))?;
    }
    Ok(())
}

pub(crate) fn insert_or_compare_memory(
    connection: &Connection,
    prepared: &PreparedMemorySource,
) -> Result<()> {
    let requested = identity(prepared);
    let inserted = connection.execute(
        "INSERT INTO memories(id,source_path,source_kind,manifest_id,created_at)\
         VALUES (?1,?2,?3,?4,?5) ON CONFLICT(id) DO NOTHING",
        params![
            prepared.id,
            requested.0,
            requested.1,
            requested.2,
            now_millis()
        ],
    )?;
    if inserted == 1 {
        return Ok(());
    }
    let existing = memory_identity(connection, &prepared.id)?.with_context(|| {
        format!(
            "memory disappeared while comparing its identity: {}",
            prepared.id
        )
    })?;
    ensure_same(&prepared.id, &existing, &requested)
}

fn memory_identity(connection: &Connection, id: &str) -> Result<Option<MemoryIdentity>> {
    connection
        .query_row(
            "SELECT source_path,source_kind,manifest_id FROM memories WHERE id=?1",
            [id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()
        .map_err(Into::into)
}

fn identity(prepared: &PreparedMemorySource) -> MemoryIdentity {
    match &prepared.source {
        PersistedMemorySource::Directory(path) => (
            path.to_string_lossy().into_owned(),
            "directory".into(),
            None,
        ),
        PersistedMemorySource::Checkpoint {
            backing_store,
            manifest_id,
        } => (
            backing_store.to_string_lossy().into_owned(),
            "checkpoint".into(),
            Some(manifest_id.clone()),
        ),
    }
}

fn ensure_same(id: &str, existing: &MemoryIdentity, requested: &MemoryIdentity) -> Result<()> {
    if existing != requested {
        bail!("memory id already identifies a different source: {id}");
    }
    Ok(())
}
