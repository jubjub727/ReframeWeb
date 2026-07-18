use std::fs;

use anyhow::Result;
use rusqlite::Connection;

use super::{IdempotencyReservation, Store};

fn temp_root(label: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!("reframe-store-{label}-{}", Store::next_id("test")))
}

#[test]
fn opens_and_upgrades_a_version_one_store() -> Result<()> {
    let root = temp_root("upgrade");
    fs::create_dir_all(&root)?;
    let database = root.join("workspace.sqlite3");
    let connection = Connection::open(&database)?;
    connection.execute_batch(include_str!("../schema.sql"))?;
    connection.execute_batch(include_str!("../migrations/0001_initial.sql"))?;
    connection.execute("INSERT INTO schema_version(version) VALUES (1)", [])?;
    connection.execute(
        "INSERT INTO memories(id,source_path,source_kind,manifest_id,created_at) \
         VALUES ('memory:test','source','directory',NULL,1)",
        [],
    )?;
    drop(connection);

    let store = Store::open(&root)?;
    let version: i64 =
        store
            .connection
            .query_row("SELECT MAX(version) FROM schema_version", [], |row| {
                row.get(0)
            })?;
    let preserved: String = store.connection.query_row(
        "SELECT id FROM memories WHERE id='memory:test'",
        [],
        |row| row.get(0),
    )?;
    assert_eq!(version, 4);
    assert_eq!(preserved, "memory:test");
    drop(store);
    fs::remove_dir_all(root)?;
    Ok(())
}

#[test]
fn rejects_a_store_from_a_newer_schema() -> Result<()> {
    let root = temp_root("future");
    fs::create_dir_all(&root)?;
    let connection = Connection::open(root.join("workspace.sqlite3"))?;
    connection.execute_batch(include_str!("../schema.sql"))?;
    connection.execute("INSERT INTO schema_version(version) VALUES (99)", [])?;
    drop(connection);

    let error = Store::open(&root).err().expect("future schema should fail");
    assert!(error.to_string().contains("newer than supported"));
    fs::remove_dir_all(root)?;
    Ok(())
}

#[test]
fn idempotency_reservations_survive_until_completion() -> Result<()> {
    let root = temp_root("idempotency");
    let store = Store::open(&root)?;
    assert_eq!(
        store.reserve_idempotency_request("key", "create", "hash")?,
        IdempotencyReservation::New
    );
    assert!(matches!(
        store.reserve_idempotency_request("key", "create", "hash")?,
        IdempotencyReservation::Pending { operation, request_hash }
            if operation == "create" && request_hash == "hash"
    ));
    store.complete_idempotency_request("key", r#"{"ok":true}"#)?;
    assert!(matches!(
        store.reserve_idempotency_request("key", "create", "hash")?,
        IdempotencyReservation::Completed { response_json, .. }
            if response_json == r#"{"ok":true}"#
    ));
    drop(store);
    fs::remove_dir_all(root)?;
    Ok(())
}

#[test]
fn workspace_summary_order_is_total_when_timestamps_match() -> Result<()> {
    let root = temp_root("summary-order");
    let store = Store::open(&root)?;
    for id in ["first", "second"] {
        store.connection.execute(
            "INSERT INTO workspaces\
             (id,name,state,worktree_path,head_manifest,created_at,updated_at) \
             VALUES (?1,?1,'active',?1,NULL,1000,1000)",
            [id],
        )?;
    }

    let summaries = store.workspace_summaries(false)?;
    assert_eq!(
        summaries
            .iter()
            .map(|summary| summary.id.as_str())
            .collect::<Vec<_>>(),
        vec!["second", "first"]
    );

    drop(store);
    fs::remove_dir_all(root)?;
    Ok(())
}

#[test]
fn protocol_retention_prunes_only_expired_terminal_rows() -> Result<()> {
    let root = temp_root("retention");
    let mut store = Store::open(&root)?;
    let cutoff = 1_000_i64;
    for (key, state, created_at) in [
        ("old-completed", "completed", cutoff - 1),
        ("recent-completed", "completed", cutoff),
        ("old-pending", "pending", cutoff - 1),
    ] {
        store.connection.execute(
            "INSERT INTO idempotency_responses\
             (key,operation,request_hash,response_json,state,created_at) \
             VALUES (?1,'create_workspace','hash','{}',?2,?3)",
            rusqlite::params![key, state, created_at],
        )?;
    }
    store.connection.execute(
        "INSERT INTO workspaces\
         (id,name,state,worktree_path,head_manifest,created_at,updated_at) \
         VALUES ('workspace','workspace','active','worktree',NULL,1,1)",
        [],
    )?;
    for (manifest_id, state, created_at, published_at) in [
        ("old-published", "published", cutoff - 2, Some(cutoff - 1)),
        ("recent-published", "published", cutoff - 1, Some(cutoff)),
        ("old-pending-publication", "pending", cutoff - 1, None),
    ] {
        store.connection.execute(
            "INSERT INTO manifests(id,workspace_id,parent_id,created_at) \
             VALUES (?1,'workspace',NULL,?2)",
            rusqlite::params![manifest_id, created_at],
        )?;
        store.connection.execute(
            "INSERT INTO checkpoint_publications\
             (manifest_id,workspace_id,workspace_name,base_memory_ids_json,retained_count,\
              state,memory_id,created_at,published_at) \
             VALUES (?1,'workspace','workspace','[]',0,?2,?3,?4,?5)",
            rusqlite::params![
                manifest_id,
                state,
                (state == "published").then_some("memory:checkpoint"),
                created_at,
                published_at
            ],
        )?;
    }

    store.prune_protocol_history_before(cutoff)?;

    let remaining_idempotency: Vec<String> = {
        let mut statement = store
            .connection
            .prepare("SELECT key FROM idempotency_responses ORDER BY key")?;
        statement
            .query_map([], |row| row.get(0))?
            .collect::<rusqlite::Result<_>>()?
    };
    assert_eq!(
        remaining_idempotency,
        vec!["old-pending", "recent-completed"]
    );
    let remaining_publications: Vec<String> = {
        let mut statement = store
            .connection
            .prepare("SELECT manifest_id FROM checkpoint_publications ORDER BY manifest_id")?;
        statement
            .query_map([], |row| row.get(0))?
            .collect::<rusqlite::Result<_>>()?
    };
    assert_eq!(
        remaining_publications,
        vec!["old-pending-publication", "recent-published"]
    );

    drop(store);
    fs::remove_dir_all(root)?;
    Ok(())
}
