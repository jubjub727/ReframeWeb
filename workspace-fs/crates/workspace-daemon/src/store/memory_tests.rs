use std::collections::BTreeMap;
use std::fs;

use anyhow::Result;

use crate::model::WorkspaceId;

use super::Store;

#[test]
fn memory_source_ids_accept_identical_registration_but_reject_remapping() -> Result<()> {
    let root = std::env::temp_dir().join(format!(
        "reframe-memory-identity-{}",
        Store::next_id("test")
    ));
    let first = root.join("first");
    let second = root.join("second");
    fs::create_dir_all(&first)?;
    fs::create_dir_all(&second)?;
    let store = Store::open(&root.join("store"))?;

    store.persist_memory_source("memory:stable", &first)?;
    store.persist_memory_source("memory:stable", &first)?;
    let error = store
        .persist_memory_source("memory:stable", &second)
        .expect_err("memory IDs are immutable");
    assert!(
        error
            .to_string()
            .contains("already identifies a different source")
    );
    assert_eq!(store.memory_path("memory:stable")?, first.canonicalize()?);

    drop(store);
    fs::remove_dir_all(root)?;
    Ok(())
}

#[test]
fn workspace_transaction_failure_releases_new_memory_ids() -> Result<()> {
    let root = std::env::temp_dir().join(format!(
        "reframe-memory-rollback-{}",
        Store::next_id("test")
    ));
    let first = root.join("first");
    let replacement = root.join("replacement");
    fs::create_dir_all(&first)?;
    fs::create_dir_all(&replacement)?;
    let mut store = Store::open(&root.join("store"))?;
    let prepared = store.prepare_directory_source("memory:released", &first)?;
    let id = WorkspaceId::parse("transaction-fails")?;

    let error = store
        .create_workspace(
            &id,
            "transaction-fails",
            &root.join("worktree"),
            &[prepared],
            &["duplicate".into(), "duplicate".into()],
            &BTreeMap::new(),
        )
        .expect_err("duplicate scratch rows should fail the transaction");
    assert!(error.to_string().contains("UNIQUE constraint failed"));
    store.ensure_workspace_id_available(id.as_str())?;
    store.persist_memory_source("memory:released", &replacement)?;
    assert_eq!(
        store.memory_path("memory:released")?,
        replacement.canonicalize()?
    );

    drop(store);
    fs::remove_dir_all(root)?;
    Ok(())
}
