use std::fs;

use anyhow::Result;

use super::Store;

#[test]
fn ordinary_store_open_does_not_scavenge_but_owned_cleanup_is_conservative() -> Result<()> {
    let root =
        std::env::temp_dir().join(format!("reframe-blob-cleanup-{}", Store::next_id("test")));
    let store = Store::open(&root)?;
    let hash = "ab00000000000000000000000000000000000000000000000000000000000000";
    let prefix = root.join("blobs/ab");
    fs::create_dir_all(&prefix)?;
    let orphan = prefix.join(format!("{hash}.tmp-{}", uuid::Uuid::new_v4()));
    let malformed = prefix.join(format!("not-a-hash.tmp-{}", uuid::Uuid::new_v4()));
    let committed = prefix.join(hash);
    fs::write(&orphan, b"orphan")?;
    fs::write(&malformed, b"keep")?;
    fs::write(&committed, b"keep")?;
    drop(store);

    let store = Store::open(&root)?;
    assert!(orphan.exists(), "Store::open must never scavenge");
    assert_eq!(store.scavenge_orphan_blob_temporaries()?, 1);
    assert!(!orphan.exists());
    assert!(malformed.exists());
    assert!(committed.exists());

    drop(store);
    fs::remove_dir_all(root)?;
    Ok(())
}
