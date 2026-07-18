use std::fs;
#[cfg(not(windows))]
use std::fs::{File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::{Context, Result, bail};

use super::Store;

#[cfg(windows)]
#[path = "blobs/windows.rs"]
mod windows;

#[cfg(windows)]
use self::windows::{create_temporary, durable_rename};

/// Immutable bytes coupled to the digest computed from those exact bytes.
///
/// Keeping the digest and allocation together lets callers retain a verified
/// resident object and publish it later without hashing the content again.
#[derive(Clone)]
pub(crate) struct VerifiedBlob {
    bytes: Arc<[u8]>,
    digest: blake3::Hash,
}

impl VerifiedBlob {
    pub(crate) fn new(bytes: Arc<[u8]>) -> Self {
        let digest = blake3::hash(&bytes);
        Self { bytes, digest }
    }

    pub(crate) fn from_prehashed(bytes: Arc<[u8]>, digest: blake3::Hash) -> Self {
        Self { bytes, digest }
    }

    pub(crate) fn verify(bytes: Arc<[u8]>, expected: &str) -> Result<Self> {
        let expected = blake3::Hash::from_hex(expected)
            .with_context(|| format!("invalid retained blob digest {expected}"))?;
        let verified = Self::new(bytes);
        if verified.digest != expected {
            bail!(
                "retained blob digest mismatch (expected {}, found {})",
                expected.to_hex(),
                verified.digest.to_hex()
            );
        }
        Ok(verified)
    }

    pub(crate) fn bytes(&self) -> &[u8] {
        &self.bytes
    }

    #[cfg_attr(windows, allow(dead_code))]
    pub(crate) fn bytes_arc(&self) -> Arc<[u8]> {
        Arc::clone(&self.bytes)
    }

    pub(crate) fn digest(&self) -> blake3::Hash {
        self.digest
    }

    pub(crate) fn hash_hex(&self) -> String {
        self.digest.to_hex().to_string()
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum BlobPublication {
    Published,
    Existing,
}

impl Store {
    pub fn put_blob(&self, bytes: &[u8]) -> Result<String> {
        self.put_blob_at_digest(bytes, blake3::hash(bytes))
    }

    pub(crate) fn put_verified_blob(&self, blob: &VerifiedBlob) -> Result<String> {
        self.put_blob_at_digest(blob.bytes(), blob.digest())
    }

    fn put_blob_at_digest(&self, bytes: &[u8], digest: blake3::Hash) -> Result<String> {
        let hash = digest.to_hex().to_string();
        let destination = blob_path(&self.root, &hash)?;
        ensure_blob(
            &destination,
            || write_blob(bytes, &destination),
            sync_blob_directories,
        )?;
        Ok(hash)
    }

    #[cfg(test)]
    pub fn read_blob(&self, hash: &str) -> Result<Vec<u8>> {
        Self::read_blob_from(&self.root, hash)
    }

    pub(crate) fn read_blob_from(root: &Path, hash: &str) -> Result<Vec<u8>> {
        fs::read(blob_path(root, hash)?).with_context(|| format!("missing retained blob {hash}"))
    }
}

fn blob_path(root: &Path, hash: &str) -> Result<PathBuf> {
    if hash.len() != 64 || !hash.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        bail!("invalid retained blob digest: {hash}");
    }
    Ok(root.join("blobs").join(&hash[..2]).join(hash))
}

fn write_blob(bytes: &[u8], destination: &Path) -> Result<BlobPublication> {
    if let Some(parent) = destination.parent() {
        fs::create_dir_all(parent)?;
    }
    let temporary = destination.with_extension(format!("tmp-{}", uuid::Uuid::new_v4()));
    let temporary = TemporaryBlob::new(temporary);
    let mut file = create_temporary(temporary.path())?;
    file.write_all(bytes)?;
    file.sync_all()?;
    drop(file);
    publish_temporary(temporary, destination, |source, destination| {
        durable_rename(source, destination)
    })
}

fn ensure_blob(
    destination: &Path,
    publish: impl FnOnce() -> Result<BlobPublication>,
    sync: impl FnOnce(&Path) -> Result<()>,
) -> Result<BlobPublication> {
    match fs::metadata(destination) {
        Ok(metadata) if metadata.is_file() => {
            sync(destination)?;
            return Ok(BlobPublication::Existing);
        }
        Ok(_) => bail!(
            "retained blob destination is not a file: {}",
            destination.display()
        ),
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(error) => return Err(error).context("inspect retained blob destination"),
    }
    let publication = publish()?;
    // Even an existing/race-winning blob may have been renamed before its
    // directory entry reached durable storage. Establish the directory
    // barrier before allowing a manifest to trust the blob.
    sync(destination)?;
    Ok(publication)
}

#[cfg(not(windows))]
fn create_temporary(path: &Path) -> io::Result<File> {
    OpenOptions::new().write(true).create_new(true).open(path)
}

#[cfg(not(windows))]
fn durable_rename(source: &Path, destination: &Path) -> io::Result<()> {
    fs::rename(source, destination)
}

fn sync_blob_directories(destination: &Path) -> Result<()> {
    let Some(prefix_directory) = destination.parent() else {
        return Ok(());
    };
    sync_directory(prefix_directory)?;
    if let Some(blob_directory) = prefix_directory.parent() {
        sync_directory(blob_directory)?;
    }
    Ok(())
}

struct TemporaryBlob {
    path: PathBuf,
}

impl TemporaryBlob {
    fn new(path: PathBuf) -> Self {
        Self { path }
    }

    fn path(&self) -> &Path {
        &self.path
    }
}

impl Drop for TemporaryBlob {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

fn publish_temporary(
    temporary: TemporaryBlob,
    destination: &Path,
    rename: impl FnOnce(&Path, &Path) -> io::Result<()>,
) -> Result<BlobPublication> {
    match rename(temporary.path(), destination) {
        Ok(()) => Ok(BlobPublication::Published),
        Err(_) if destination.is_file() => Ok(BlobPublication::Existing),
        Err(error) => Err(error).with_context(|| {
            format!(
                "publish retained blob {} to {}",
                temporary.path().display(),
                destination.display()
            )
        }),
    }
}

#[cfg(unix)]
fn sync_directory(path: &Path) -> Result<()> {
    fs::File::open(path)?.sync_all()?;
    Ok(())
}

#[cfg(not(unix))]
fn sync_directory(_path: &Path) -> Result<()> {
    Ok(())
}

#[cfg(test)]
#[path = "blobs/tests.rs"]
mod tests;
