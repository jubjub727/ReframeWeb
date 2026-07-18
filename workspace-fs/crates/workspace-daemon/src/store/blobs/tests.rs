use std::fs;
use std::io;

use anyhow::Result;

use super::{Store, TemporaryBlob, publish_temporary};

fn temp_root(label: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!("reframe-blob-{label}-{}", Store::next_id("test")))
}

#[test]
fn put_blob_publishes_synced_content_without_temporary_files() -> Result<()> {
    let root = temp_root("publish");
    let store = Store::open(&root)?;
    let hash = store.put_blob(b"durable content")?;
    assert_eq!(store.read_blob(&hash)?, b"durable content");
    assert_eq!(store.put_blob(b"durable content")?, hash);

    let parent = root.join("blobs").join(&hash[..2]);
    let names = fs::read_dir(parent)?
        .map(|entry| entry.map(|entry| entry.file_name()))
        .collect::<io::Result<Vec<_>>>()?;
    assert_eq!(names, vec![std::ffi::OsString::from(hash)]);

    drop(store);
    fs::remove_dir_all(root)?;
    Ok(())
}

#[test]
fn failed_publish_removes_its_temporary_file() -> Result<()> {
    let root = temp_root("failed-rename");
    fs::create_dir_all(&root)?;
    let temporary_path = root.join("blob.tmp");
    let destination = root.join("blob");
    fs::write(&temporary_path, b"content")?;

    let error = publish_temporary(
        TemporaryBlob::new(temporary_path.clone()),
        &destination,
        |_, _| Err(io::Error::new(io::ErrorKind::PermissionDenied, "denied")),
    )
    .expect_err("rename error should be returned");
    assert!(error.to_string().contains("publish retained blob"));
    assert!(!temporary_path.exists());
    assert!(!destination.exists());

    fs::remove_dir_all(root)?;
    Ok(())
}

#[test]
fn raced_publish_also_removes_its_temporary_file() -> Result<()> {
    let root = temp_root("raced-rename");
    fs::create_dir_all(&root)?;
    let temporary_path = root.join("blob.tmp");
    let destination = root.join("blob");
    fs::write(&temporary_path, b"temporary")?;
    fs::write(&destination, b"winner")?;

    publish_temporary(
        TemporaryBlob::new(temporary_path.clone()),
        &destination,
        |_, _| Err(io::Error::new(io::ErrorKind::AlreadyExists, "raced")),
    )?;
    assert!(!temporary_path.exists());
    assert_eq!(fs::read(&destination)?, b"winner");

    fs::remove_dir_all(root)?;
    Ok(())
}
