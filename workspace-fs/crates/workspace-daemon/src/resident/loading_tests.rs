use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Duration;

use anyhow::{Result, bail};

use super::ResidentWorkspace;
use super::loading::{MAX_COLD_LOAD_WORKERS, parallel_map_ordered, worker_count};
use super::storage::prepare_record_load;
use crate::model::{BackingBlobLocator, FileRecord, RecordSource};
use crate::paths::NormalizedPath;
use crate::session;
use crate::store::Store;

fn temp_root(label: &str) -> PathBuf {
    std::env::temp_dir().join(format!("reframe-{label}-{}", Store::next_id("test")))
}

#[test]
fn worker_count_is_bounded_by_work_hardware_and_ceiling() {
    assert_eq!(worker_count(0, 64), 0);
    assert_eq!(worker_count(2, 64), 2);
    assert_eq!(worker_count(100, 2), 2);
    assert_eq!(worker_count(100, 64), MAX_COLD_LOAD_WORKERS);
}

#[test]
fn parallel_map_preserves_input_order_and_bounds_concurrency() -> Result<()> {
    let active = AtomicUsize::new(0);
    let peak = AtomicUsize::new(0);
    let items = (0..12).collect::<Vec<_>>();
    let loaded = parallel_map_ordered(&items, 3, |item| {
        let now = active.fetch_add(1, Ordering::SeqCst) + 1;
        peak.fetch_max(now, Ordering::SeqCst);
        std::thread::sleep(Duration::from_millis((12 - item) as u64));
        active.fetch_sub(1, Ordering::SeqCst);
        Ok(*item)
    })?;

    assert_eq!(loaded, items);
    assert!((2..=3).contains(&peak.load(Ordering::SeqCst)));
    Ok(())
}

#[test]
fn parallel_errors_are_reported_in_input_order() {
    let error = parallel_map_ordered(&(0..4).collect::<Vec<_>>(), 4, |item| {
        if *item == 1 {
            std::thread::sleep(Duration::from_millis(10));
            bail!("first ordered failure");
        }
        if *item == 3 {
            bail!("later failure that finishes first");
        }
        Ok(*item)
    })
    .expect_err("parallel load should fail");

    assert_eq!(error.to_string(), "first ordered failure");
}

#[test]
fn cold_memory_load_deduplicates_and_verifies_content() -> Result<()> {
    let root = temp_root("parallel-resident-load");
    let memory = root.join("memory");
    fs::create_dir_all(memory.join("nested"))?;
    fs::write(memory.join("a.txt"), b"shared")?;
    fs::write(memory.join("nested/b.txt"), b"shared")?;
    fs::write(memory.join("z.txt"), b"unique")?;
    let mut store = Store::open(&root.join("store"))?;
    store.persist_memory_source("memory:parallel", &memory)?;
    session::create(
        &mut store,
        "parallel",
        Some("parallel"),
        &["memory:parallel".into()],
        &[],
    )?;

    let resident = ResidentWorkspace::load(&store, "parallel")?;
    let first = resident
        .file("a.txt")
        .expect("first duplicate")
        .snapshot()?;
    let second = resident
        .file("nested/b.txt")
        .expect("second duplicate")
        .snapshot()?;
    assert!(Arc::ptr_eq(&first, &second));
    assert_eq!(
        resident.entries(""),
        vec![
            ("a.txt".into(), false, 6),
            ("nested".into(), true, 0),
            ("z.txt".into(), false, 6),
        ]
    );

    drop(resident);
    fs::write(memory.join("a.txt"), b"changed after baseline")?;
    let error = ResidentWorkspace::load(&store, "parallel")
        .err()
        .expect("changed filesystem memory must be rejected");
    assert!(error.to_string().contains("digest mismatch"));

    drop(store);
    fs::remove_dir_all(root)?;
    Ok(())
}

#[test]
fn checkpoint_blob_load_does_not_open_its_backing_store() -> Result<()> {
    let root = temp_root("direct-checkpoint-load");
    let backing_root = root.join("backing");
    let hash = {
        let store = Store::open(&backing_root)?;
        store.put_blob(b"checkpoint bytes")?
    };
    let database = backing_root.join("workspace.sqlite3");
    fs::remove_file(&database)?;
    let record = FileRecord {
        path: NormalizedPath::parse_str("checkpoint.txt")?,
        hash: hash.clone(),
        size: 16,
        source: RecordSource::BackingBlob(BackingBlobLocator {
            store_root: backing_root.clone(),
            hash,
        }),
    };

    let load = prepare_record_load(&root.join("unused-local-store"), &record, &HashMap::new())?;
    assert_eq!(load.load_verified()?.bytes(), b"checkpoint bytes");
    assert!(!database.exists());

    fs::remove_dir_all(root)?;
    Ok(())
}
