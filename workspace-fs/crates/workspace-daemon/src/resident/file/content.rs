use std::sync::Arc;

use crate::store::VerifiedBlob;

use super::overlay::PagedContent;

pub(super) enum FileContent {
    Shared(VerifiedBlob),
    Overlay(PagedContent),
    Owned(OwnedContent),
}

pub(super) struct OwnedContent {
    bytes: Vec<u8>,
    digest: Option<blake3::Hash>,
}

impl FileContent {
    pub(super) fn owned(bytes: Vec<u8>) -> Self {
        Self::Owned(OwnedContent {
            bytes,
            digest: None,
        })
    }

    pub(super) fn len(&self) -> usize {
        match self {
            Self::Shared(blob) => blob.bytes().len(),
            Self::Overlay(content) => content.len(),
            Self::Owned(content) => content.bytes.len(),
        }
    }

    pub(super) fn copy_into(&self, offset: usize, output: &mut [u8]) -> usize {
        match self {
            Self::Shared(blob) => copy_slice(blob.bytes(), offset, output),
            Self::Overlay(content) => content.copy_into(offset, output),
            Self::Owned(content) => copy_slice(&content.bytes, offset, output),
        }
    }

    pub(super) fn digest(&mut self) -> blake3::Hash {
        match self {
            Self::Shared(blob) => blob.digest(),
            Self::Overlay(content) => content.digest(),
            Self::Owned(content) => *content
                .digest
                .get_or_insert_with(|| blake3::hash(&content.bytes)),
        }
    }

    pub(super) fn seal(&mut self) -> VerifiedBlob {
        if let Self::Shared(blob) = self {
            return blob.clone();
        }
        let digest = self.digest();
        let bytes: Arc<[u8]> = match self {
            Self::Overlay(content) => content.materialize().into(),
            Self::Owned(content) => std::mem::take(&mut content.bytes).into(),
            Self::Shared(_) => unreachable!("shared content returned above"),
        };
        let blob = VerifiedBlob::from_prehashed(bytes, digest);
        *self = Self::Shared(blob.clone());
        blob
    }

    pub(super) fn write(&mut self, offset: usize, end: usize, data: &[u8]) {
        match self {
            Self::Owned(content) => content.write(offset, end, data),
            Self::Overlay(content) => content.write(offset, data),
            Self::Shared(blob) if offset == 0 && end == blob.bytes().len() => {
                *self = Self::owned(data.to_vec());
            }
            Self::Shared(blob) => {
                let mut content = PagedContent::new(blob.clone());
                content.write(offset, data);
                *self = Self::Overlay(content);
            }
        }
    }

    pub(super) fn resize(&mut self, size: usize) {
        if size == self.len() {
            return;
        }
        match self {
            Self::Owned(content) => content.resize(size),
            Self::Overlay(_) | Self::Shared(_) if size == 0 => {
                *self = Self::owned(Vec::new());
            }
            Self::Overlay(content) => content.resize(size),
            Self::Shared(blob) => {
                let mut content = PagedContent::new(blob.clone());
                content.resize(size);
                *self = Self::Overlay(content);
            }
        }
    }

    #[cfg(test)]
    pub(super) fn storage_metrics(&self) -> (&'static str, usize) {
        match self {
            Self::Shared(_) => ("shared", 0),
            Self::Overlay(content) => ("overlay", content.allocated_bytes()),
            Self::Owned(content) => ("owned", content.bytes.capacity()),
        }
    }
}

impl OwnedContent {
    fn write(&mut self, offset: usize, end: usize, data: &[u8]) {
        if self.bytes.len() < offset {
            self.bytes.resize(offset, 0);
        }
        if self.bytes.len() < end {
            self.bytes.resize(end, 0);
        }
        self.bytes[offset..end].copy_from_slice(data);
        self.digest = None;
    }

    fn resize(&mut self, size: usize) {
        self.bytes.resize(size, 0);
        self.digest = None;
    }
}

fn copy_slice(bytes: &[u8], offset: usize, output: &mut [u8]) -> usize {
    if offset >= bytes.len() {
        return 0;
    }
    let count = output.len().min(bytes.len() - offset);
    output[..count].copy_from_slice(&bytes[offset..offset + count]);
    count
}
