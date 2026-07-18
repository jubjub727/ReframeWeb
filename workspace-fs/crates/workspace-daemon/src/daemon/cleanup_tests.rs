use std::fs;

use anyhow::Result;

use crate::local_socket::StoreLock;
use crate::store::Store;

use super::Daemon;

#[test]
fn exclusively_owned_daemon_startup_scavenges_blob_temporaries() -> Result<()> {
    let root =
        std::env::temp_dir().join(format!("reframe-daemon-cleanup-{}", Store::next_id("test")));
    let store = Store::open(&root)?;
    let hash = "ab00000000000000000000000000000000000000000000000000000000000000";
    let prefix = root.join("blobs/ab");
    fs::create_dir_all(&prefix)?;
    let orphan = prefix.join(format!("{hash}.tmp-{}", uuid::Uuid::new_v4()));
    fs::write(&orphan, b"orphan")?;
    drop(store);

    let lock = StoreLock::acquire(&root)?;
    let daemon = Daemon::open_with_exclusive_ownership(&root)?;
    assert!(!orphan.exists());

    drop(daemon);
    drop(lock);
    fs::remove_dir_all(root)?;
    Ok(())
}
