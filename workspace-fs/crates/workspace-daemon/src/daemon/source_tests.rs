use std::collections::HashMap;
use std::fs;
use std::sync::Arc;

use anyhow::Result;
use serde_json::json;

use crate::protocol::Request;
use crate::resident::ResidentWorkspace;
use crate::store::Store;

use super::Daemon;

fn daemon(root: &std::path::Path) -> Result<Daemon> {
    Ok(Daemon {
        store: Store::open(root)?,
        content_cache: crate::resident::ContentCache::new(1024 * 1024),
        residents: HashMap::new(),
        process_idempotency_requests: Default::default(),
        mounts: HashMap::new(),
    })
}

#[test]
fn workspace_creation_seeds_the_resident_cache_for_mount() -> Result<()> {
    let root =
        std::env::temp_dir().join(format!("reframe-memory-cache-{}", Store::next_id("test")));
    let source = root.join("source");
    fs::create_dir_all(&source)?;
    fs::write(source.join("note.txt"), b"snapshot at create")?;
    let mut daemon = daemon(&root.join("store"))?;

    assert!(
        daemon
            .handle(create_request("first", "create-cached", &source)?)
            .ok
    );
    fs::write(source.join("note.txt"), b"changed after create")?;

    let resident = daemon
        .residents
        .get("existing")
        .expect("workspace creation should prepare resident content");
    assert_eq!(
        resident
            .file("note.txt")
            .expect("cached file")
            .snapshot()?
            .as_ref(),
        b"snapshot at create"
    );

    drop(daemon);
    fs::remove_dir_all(root)?;
    Ok(())
}

#[test]
fn applying_policy_replaces_the_eager_matcher_without_losing_resident_edits() -> Result<()> {
    let root =
        std::env::temp_dir().join(format!("reframe-policy-refresh-{}", Store::next_id("test")));
    let source = root.join("source");
    fs::create_dir_all(&source)?;
    fs::write(source.join("note.txt"), b"baseline")?;
    let mut daemon = daemon(&root.join("store"))?;
    assert!(
        daemon
            .handle(create_request("create", "create", &source)?)
            .ok
    );

    let before = Arc::clone(daemon.residents.get("existing").expect("eager resident"));
    before.replace("unsaved.txt", b"resident edit".to_vec())?;
    assert!(!before.is_scratch("generated/output.txt"));
    let applied = daemon.handle(serde_json::from_value(json!({
        "request_id": "policy",
        "idempotency_key": "policy",
        "operation": "apply_policy",
        "session_id": "existing",
        "scratch_paths": ["generated/**"],
    }))?);

    assert!(applied.ok, "{:?}", applied.error);
    let after = daemon
        .residents
        .get("existing")
        .expect("refreshed resident");
    assert!(!Arc::ptr_eq(&before, after));
    assert!(after.is_scratch("generated/output.txt"));
    assert_eq!(
        after
            .file("unsaved.txt")
            .expect("uncheckpointed edit")
            .snapshot()?
            .as_ref(),
        b"resident edit"
    );

    drop(before);
    drop(daemon);
    fs::remove_dir_all(root)?;
    Ok(())
}

fn create_request(request_id: &str, key: &str, source_path: &std::path::Path) -> Result<Request> {
    Ok(serde_json::from_value(json!({
        "request_id": request_id,
        "idempotency_key": key,
        "operation": "create_workspace",
        "name": "test",
        "session_id": "existing",
        "memory_sources": [{
            "source_kind": "directory",
            "memory_id": "memory:shared",
            "source_path": source_path,
        }],
        "scratch_paths": [],
    }))?)
}

#[test]
fn failed_create_cannot_remap_an_existing_workspace_baseline() -> Result<()> {
    let root =
        std::env::temp_dir().join(format!("reframe-memory-remap-{}", Store::next_id("test")));
    let original = root.join("original");
    let replacement = root.join("replacement");
    fs::create_dir_all(&original)?;
    fs::create_dir_all(&replacement)?;
    fs::write(original.join("note.txt"), b"original")?;
    fs::write(replacement.join("note.txt"), b"replacement")?;

    let mut daemon = daemon(&root.join("store"))?;
    assert!(
        daemon
            .handle(create_request("first", "create-first", &original)?)
            .ok
    );
    let rejected = daemon.handle(create_request("second", "create-second", &replacement)?);
    assert!(!rejected.ok);
    assert!(
        rejected
            .error
            .expect("operation error")
            .message
            .contains("already identifies a different source")
    );

    assert_eq!(
        daemon.store.memory_path("memory:shared")?,
        original.canonicalize()?
    );
    let resident = ResidentWorkspace::load(&daemon.store, "existing")?;
    assert_eq!(
        resident
            .file("note.txt")
            .expect("projected file")
            .snapshot()?
            .as_ref(),
        b"original"
    );

    drop(resident);
    drop(daemon);
    fs::remove_dir_all(root)?;
    Ok(())
}

#[test]
fn source_preflight_failure_leaves_no_ids_or_worktree() -> Result<()> {
    let root = std::env::temp_dir().join(format!(
        "reframe-source-preflight-{}",
        Store::next_id("test")
    ));
    let first = root.join("first");
    let replacement = root.join("replacement");
    fs::create_dir_all(&first)?;
    fs::create_dir_all(&replacement)?;
    let missing = root.join("missing");
    let store_root = root.join("store");
    let mut daemon = daemon(&store_root)?;
    let request = serde_json::from_value(json!({
        "request_id": "atomic",
        "idempotency_key": "atomic-create",
        "operation": "create_workspace",
        "name": "atomic",
        "session_id": "atomic",
        "memory_sources": [
            {
                "source_kind": "directory",
                "memory_id": "memory:released",
                "source_path": first,
            },
            {
                "source_kind": "directory",
                "memory_id": "memory:invalid",
                "source_path": missing,
            },
        ],
        "scratch_paths": [],
    }))?;

    let response = daemon.handle(request);
    assert!(!response.ok);
    assert!(!store_root.join("sessions/atomic").exists());
    let reuse = serde_json::from_value(json!({
        "request_id": "reuse",
        "idempotency_key": "reuse-create",
        "operation": "create_workspace",
        "name": "reuse",
        "session_id": "reuse",
        "memory_sources": [{
            "source_kind": "directory",
            "memory_id": "memory:released",
            "source_path": replacement,
        }],
        "scratch_paths": [],
    }))?;
    assert!(daemon.handle(reuse).ok);
    assert_eq!(
        daemon.store.memory_path("memory:released")?,
        replacement.canonicalize()?
    );

    drop(daemon);
    fs::remove_dir_all(root)?;
    Ok(())
}

#[test]
fn late_transaction_failure_rolls_back_source_id_and_worktree() -> Result<()> {
    let root = std::env::temp_dir().join(format!(
        "reframe-create-rollback-{}",
        Store::next_id("test")
    ));
    let first = root.join("first");
    let replacement = root.join("replacement");
    fs::create_dir_all(&first)?;
    fs::create_dir_all(&replacement)?;
    fs::write(first.join("note.txt"), b"first")?;
    fs::write(replacement.join("note.txt"), b"replacement")?;
    let store_root = root.join("store");
    let mut daemon = daemon(&store_root)?;
    let connection = rusqlite::Connection::open(store_root.join("workspace.sqlite3"))?;
    connection.execute_batch(
        "CREATE TRIGGER fail_workspace_insert BEFORE INSERT ON workspaces \
         BEGIN SELECT RAISE(FAIL, 'injected workspace failure'); END;",
    )?;

    let failed = serde_json::from_value(json!({
        "request_id": "late-failure",
        "idempotency_key": "late-failure",
        "operation": "create_workspace",
        "name": "late-failure",
        "session_id": "late-failure",
        "memory_sources": [{
            "source_kind": "directory",
            "memory_id": "memory:late-released",
            "source_path": first,
        }],
        "scratch_paths": [],
    }))?;
    assert!(!daemon.handle(failed).ok);
    assert!(!store_root.join("sessions/late-failure").exists());
    connection.execute_batch("DROP TRIGGER fail_workspace_insert;")?;
    drop(connection);

    let reuse = serde_json::from_value(json!({
        "request_id": "late-reuse",
        "idempotency_key": "late-reuse",
        "operation": "create_workspace",
        "name": "late-reuse",
        "session_id": "late-reuse",
        "memory_sources": [{
            "source_kind": "directory",
            "memory_id": "memory:late-released",
            "source_path": replacement,
        }],
        "scratch_paths": [],
    }))?;
    assert!(daemon.handle(reuse).ok);
    assert_eq!(
        daemon.store.memory_path("memory:late-released")?,
        replacement.canonicalize()?
    );

    drop(daemon);
    fs::remove_dir_all(root)?;
    Ok(())
}
