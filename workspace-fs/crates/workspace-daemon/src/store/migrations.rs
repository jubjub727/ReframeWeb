use anyhow::{Result, bail};
use rusqlite::{Connection, params};

struct Migration {
    version: i64,
    name: &'static str,
    sql: &'static str,
}

const MIGRATIONS: &[Migration] = &[
    Migration {
        version: 1,
        name: "initial",
        sql: include_str!("../migrations/0001_initial.sql"),
    },
    Migration {
        version: 2,
        name: "idempotency_digest",
        sql: include_str!("../migrations/0002_idempotency_digest.sql"),
    },
    Migration {
        version: 3,
        name: "checkpoint_publication_outbox",
        sql: include_str!("../migrations/0003_checkpoint_publication_outbox.sql"),
    },
    Migration {
        version: 4,
        name: "protocol_retention_indexes",
        sql: include_str!("../migrations/0004_protocol_retention.sql"),
    },
];

pub(super) fn apply(connection: &mut Connection) -> Result<()> {
    connection.execute_batch(include_str!("../schema.sql"))?;
    let applied = applied_versions(connection)?;
    let latest = MIGRATIONS.last().map_or(0, |migration| migration.version);
    if applied.last().is_some_and(|version| *version > latest) {
        bail!(
            "workspace store schema {} is newer than supported version {latest}",
            applied.last().unwrap()
        );
    }
    for (index, version) in applied.iter().enumerate() {
        let expected = index as i64 + 1;
        if *version != expected {
            bail!("workspace store migration history has a gap before version {version}");
        }
    }
    for migration in MIGRATIONS
        .iter()
        .filter(|migration| !applied.contains(&migration.version))
    {
        let transaction = connection.transaction()?;
        transaction
            .execute_batch(migration.sql)
            .map_err(|error| anyhow::anyhow!("apply migration {}: {error}", migration.name))?;
        transaction.execute(
            "INSERT INTO schema_version(version) VALUES (?1)",
            params![migration.version],
        )?;
        transaction.commit()?;
    }
    Ok(())
}

fn applied_versions(connection: &Connection) -> Result<Vec<i64>> {
    let mut statement =
        connection.prepare("SELECT version FROM schema_version ORDER BY version")?;
    let versions = statement.query_map([], |row| row.get(0))?;
    versions
        .collect::<rusqlite::Result<Vec<_>>>()
        .map_err(Into::into)
}
