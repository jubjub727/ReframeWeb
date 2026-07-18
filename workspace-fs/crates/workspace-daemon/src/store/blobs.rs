use std::fs;
#[cfg(not(windows))]
use std::fs::{File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};

use super::Store;

#[cfg(windows)]
#[path = "blobs/windows.rs"]
mod windows;

#[cfg(windows)]
use self::windows::{create_temporary, durable_rename};

impl Store {
    pub fn put_blob(&self, bytes: &[u8]) -> Result<String> {
        let hash = blake3::hash(bytes).to_hex().to_string();
        let destination = self.blob_path(&hash);
        if !destination.exists() {
            if let Some(parent) = destination.parent() {
                fs::create_dir_all(parent)?;
            }
            let temporary = destination.with_extension(format!("tmp-{}", uuid::Uuid::new_v4()));
            let temporary = TemporaryBlob::new(temporary);
            let mut file = create_temporary(temporary.path())?;
            file.write_all(bytes)?;
            file.sync_all()?;
            drop(file);
            publish_temporary(temporary, &destination, |source, destination| {
                durable_rename(source, destination)
            })?;
        }
        sync_blob_directories(&destination)?;
        Ok(hash)
    }

    pub fn read_blob(&self, hash: &str) -> Result<Vec<u8>> {
        fs::read(self.blob_path(hash)).with_context(|| format!("missing retained blob {hash}"))
    }

    fn blob_path(&self, hash: &str) -> PathBuf {
        self.root.join("blobs").join(&hash[..2]).join(hash)
    }
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
) -> Result<()> {
    match rename(temporary.path(), destination) {
        Ok(()) => Ok(()),
        Err(_) if destination.is_file() => Ok(()),
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
