use std::cell::Cell;
use std::fs;
use std::io;
use std::sync::Arc;

use anyhow::Result;

use super::{BlobPublication, Store, TemporaryBlob, VerifiedBlob, ensure_blob, publish_temporary};

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
fn verified_blob_publishes_without_rehashing_at_the_store_boundary() -> Result<()> {
    let root = temp_root("verified");
    let store = Store::open(&root)?;
    let blob = VerifiedBlob::new(Arc::from(&b"already hashed"[..]));

    let hash = store.put_verified_blob(&blob)?;

    assert_eq!(hash, blob.hash_hex());
    assert_eq!(store.read_blob(&hash)?, blob.bytes());
    drop(store);
    fs::remove_dir_all(root)?;
    Ok(())
}

#[test]
fn verified_blob_rejects_a_digest_for_different_content() -> Result<()> {
    let root = temp_root("mismatch");
    let store = Store::open(&root)?;
    let expected = blake3::hash(b"expected").to_hex().to_string();

    let error = VerifiedBlob::verify(Arc::from(&b"different"[..]), &expected)
        .err()
        .expect("mismatched content must not become a verified blob");

    assert!(error.to_string().contains("digest mismatch"));
    let malformed = VerifiedBlob::verify(Arc::from(&b"different"[..]), "not-a-digest")
        .err()
        .expect("malformed digests must be rejected");
    assert!(
        malformed
            .to_string()
            .contains("invalid retained blob digest")
    );
    assert!(fs::read_dir(root.join("blobs"))?.next().is_none());
    drop(store);
    fs::remove_dir_all(root)?;
    Ok(())
}

#[test]
fn existing_blob_skips_publication_but_still_syncs_directories() -> Result<()> {
    let root = temp_root("existing-fast-path");
    fs::create_dir_all(&root)?;
    let destination = root.join("blob");
    fs::write(&destination, b"existing")?;

    let syncs = Cell::new(0);
    let publication = ensure_blob(
        &destination,
        || panic!("an existing blob must not be republished"),
        |_| {
            syncs.set(syncs.get() + 1);
            Ok(())
        },
    )?;

    assert_eq!(publication, BlobPublication::Existing);
    assert_eq!(syncs.get(), 1);
    assert_eq!(fs::read(&destination)?, b"existing");
    fs::remove_dir_all(root)?;
    Ok(())
}

#[test]
fn publication_race_still_syncs_the_winning_blob_directories() -> Result<()> {
    let root = temp_root("raced-sync");
    fs::create_dir_all(&root)?;
    let destination = root.join("blob");
    let syncs = Cell::new(0);

    let publication = ensure_blob(
        &destination,
        || {
            fs::write(&destination, b"winner")?;
            Ok(BlobPublication::Existing)
        },
        |_| {
            syncs.set(syncs.get() + 1);
            Ok(())
        },
    )?;

    assert_eq!(publication, BlobPublication::Existing);
    assert_eq!(syncs.get(), 1);
    assert_eq!(fs::read(&destination)?, b"winner");
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

    let publication = publish_temporary(
        TemporaryBlob::new(temporary_path.clone()),
        &destination,
        |_, _| Err(io::Error::new(io::ErrorKind::AlreadyExists, "raced")),
    )?;
    assert_eq!(publication, BlobPublication::Existing);
    assert!(!temporary_path.exists());
    assert_eq!(fs::read(&destination)?, b"winner");

    fs::remove_dir_all(root)?;
    Ok(())
}
