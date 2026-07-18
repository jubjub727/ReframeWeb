use std::path::PathBuf;

use anyhow::{Context, Result, bail};

use crate::paths::NormalizedPath;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FileRecord {
    pub path: NormalizedPath,
    pub hash: String,
    pub size: u64,
    pub source: RecordSource,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RecordSource {
    Directory,
    Overlay,
    Blob,
    Resident,
    Tombstone,
    Memory(MemoryLocator),
    BackingBlob(BackingBlobLocator),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MemoryLocator {
    pub memory_id: String,
    pub relative_path: NormalizedPath,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BackingBlobLocator {
    pub store_root: PathBuf,
    pub hash: String,
}

impl RecordSource {
    pub fn from_storage(kind: &str, reference: Option<&str>) -> Result<Self> {
        match kind {
            "directory" => Ok(Self::Directory),
            "overlay" => Ok(Self::Overlay),
            "blob" => Ok(Self::Blob),
            "resident" => Ok(Self::Resident),
            "tombstone" => Ok(Self::Tombstone),
            "memory" => parse_memory(reference),
            "backing_blob" => parse_backing_blob(reference),
            kind => bail!("unsupported file-record source kind: {kind}"),
        }
    }

    pub fn kind(&self) -> &'static str {
        match self {
            Self::Directory => "directory",
            Self::Overlay => "overlay",
            Self::Blob => "blob",
            Self::Resident => "resident",
            Self::Tombstone => "tombstone",
            Self::Memory(_) => "memory",
            Self::BackingBlob(_) => "backing_blob",
        }
    }

    pub fn reference_json(&self) -> Result<Option<String>> {
        match self {
            Self::Memory(locator) => Ok(Some(serde_json::to_string(&(
                &locator.memory_id,
                locator.relative_path.as_str(),
            ))?)),
            Self::BackingBlob(locator) => Ok(Some(serde_json::to_string(&(
                &locator.store_root,
                &locator.hash,
            ))?)),
            _ => Ok(None),
        }
    }

    pub fn is_projected_file(&self) -> bool {
        !matches!(self, Self::Directory | Self::Tombstone)
    }
}

fn parse_memory(reference: Option<&str>) -> Result<RecordSource> {
    let reference = reference.context("memory entry is missing its reference")?;
    let (memory_id, relative_path): (String, String) =
        serde_json::from_str(reference).context("invalid memory reference")?;
    Ok(RecordSource::Memory(MemoryLocator {
        memory_id,
        relative_path: NormalizedPath::parse_str(&relative_path)?,
    }))
}

fn parse_backing_blob(reference: Option<&str>) -> Result<RecordSource> {
    let reference = reference.context("backing-store entry is missing its reference")?;
    let (store_root, hash): (PathBuf, String) =
        serde_json::from_str(reference).context("invalid backing-store reference")?;
    Ok(RecordSource::BackingBlob(BackingBlobLocator {
        store_root,
        hash,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn structured_locators_preserve_legacy_storage_shape() -> Result<()> {
        let source = RecordSource::Memory(MemoryLocator {
            memory_id: "memory:one".into(),
            relative_path: NormalizedPath::parse_str("notes/brief.md")?,
        });
        let encoded = source.reference_json()?.unwrap();
        assert_eq!(
            RecordSource::from_storage(source.kind(), Some(&encoded))?,
            source
        );
        Ok(())
    }
}
