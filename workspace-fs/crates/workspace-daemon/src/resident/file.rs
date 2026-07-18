use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, RwLock};

use anyhow::{Context, Result};

use crate::store::VerifiedBlob;

use super::lock_error;

mod content;
mod overlay;

use self::content::FileContent;

#[derive(Clone)]
pub struct ResidentFile {
    inner: Arc<ResidentFileInner>,
}

struct ResidentFileInner {
    content: RwLock<FileContent>,
    dirty: AtomicBool,
}

impl ResidentFile {
    pub(super) fn shared(blob: VerifiedBlob) -> Self {
        Self {
            inner: Arc::new(ResidentFileInner {
                content: RwLock::new(FileContent::Shared(blob)),
                dirty: AtomicBool::new(false),
            }),
        }
    }

    pub(super) fn owned(bytes: Vec<u8>) -> Self {
        Self {
            inner: Arc::new(ResidentFileInner {
                content: RwLock::new(FileContent::owned(bytes)),
                dirty: AtomicBool::new(true),
            }),
        }
    }

    pub fn len(&self) -> usize {
        self.inner
            .content
            .read()
            .map(|content| content.len())
            .unwrap_or_default()
    }

    pub fn read_range(&self, offset: u64, size: usize) -> Result<Vec<u8>> {
        let content = self.inner.content.read().map_err(lock_error)?;
        let start = usize::try_from(offset).context("read offset exceeds address space")?;
        if start >= content.len() {
            return Ok(Vec::new());
        }
        let mut output = vec![0; size.min(content.len() - start)];
        content.copy_into(start, &mut output);
        Ok(output)
    }

    pub fn copy_into(&self, offset: u64, output: &mut [u8]) -> Result<usize> {
        let start = usize::try_from(offset).context("read offset exceeds address space")?;
        let content = self.inner.content.read().map_err(lock_error)?;
        Ok(content.copy_into(start, output))
    }

    pub fn with_bytes<T>(&self, read: impl FnOnce(&[u8]) -> T) -> Result<T> {
        let blob = self.verified_blob()?;
        Ok(read(blob.bytes()))
    }

    #[cfg_attr(windows, allow(dead_code))]
    pub fn snapshot(&self) -> Result<Arc<[u8]>> {
        Ok(self.verified_blob()?.bytes_arc())
    }

    pub fn hash_hex(&self) -> Result<String> {
        let mut content = self.inner.content.write().map_err(lock_error)?;
        Ok(content.digest().to_hex().to_string())
    }

    pub fn content_id(&self) -> Result<[u8; 32]> {
        let mut content = self.inner.content.write().map_err(lock_error)?;
        Ok(*content.digest().as_bytes())
    }

    pub(crate) fn verified_blob(&self) -> Result<VerifiedBlob> {
        let mut content = self.inner.content.write().map_err(lock_error)?;
        Ok(content.seal())
    }

    pub(super) fn mark_dirty(&self) -> bool {
        !self.inner.dirty.swap(true, Ordering::Relaxed)
    }

    pub(super) fn mark_clean(&self) {
        self.inner.dirty.store(false, Ordering::Relaxed);
    }

    pub(crate) fn same_identity(&self, other: &Self) -> bool {
        Arc::ptr_eq(&self.inner, &other.inner)
    }

    pub(super) fn replace(&self, bytes: Vec<u8>) -> Result<(usize, usize)> {
        let mut content = self.inner.content.write().map_err(lock_error)?;
        let previous = content.len();
        let current = bytes.len();
        *content = FileContent::owned(bytes);
        Ok((previous, current))
    }

    pub(super) fn write(&self, offset: u64, data: &[u8]) -> Result<(usize, usize)> {
        let offset = usize::try_from(offset).context("write offset exceeds address space")?;
        let end = offset
            .checked_add(data.len())
            .context("write length overflow")?;
        let mut content = self.inner.content.write().map_err(lock_error)?;
        let previous = content.len();
        if !data.is_empty() {
            content.write(offset, end, data);
        }
        Ok((previous, content.len()))
    }

    pub(super) fn resize(&self, size: u64) -> Result<(usize, usize)> {
        let size = usize::try_from(size).context("file size exceeds address space")?;
        let mut content = self.inner.content.write().map_err(lock_error)?;
        let previous = content.len();
        content.resize(size);
        Ok((previous, size))
    }

    #[cfg(test)]
    pub(super) fn storage_metrics(&self) -> (&'static str, usize) {
        self.inner
            .content
            .read()
            .map(|content| content.storage_metrics())
            .unwrap_or(("poisoned", 0))
    }
}
