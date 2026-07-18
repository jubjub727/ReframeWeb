use std::collections::HashMap;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};

use crate::model::{FileRecord, RecordSource};
use crate::paths::native_path;
use crate::store::{Store, VerifiedBlob};

pub(super) struct PreparedRecordLoad {
    expected_hash: String,
    source: PreparedSource,
}

enum PreparedSource {
    Blob { root: PathBuf, hash: String },
    Memory(PathBuf),
}

pub(super) fn resolve_memory_roots<'a>(
    store: &Store,
    records: impl Iterator<Item = &'a FileRecord>,
) -> Result<HashMap<String, PathBuf>> {
    let mut roots = HashMap::new();
    for record in records {
        let RecordSource::Memory(locator) = &record.source else {
            continue;
        };
        if !roots.contains_key(&locator.memory_id) {
            roots.insert(
                locator.memory_id.clone(),
                store.memory_path(&locator.memory_id)?,
            );
        }
    }
    Ok(roots)
}

pub(super) fn prepare_record_load(
    store_root: &Path,
    record: &FileRecord,
    memory_roots: &HashMap<String, PathBuf>,
) -> Result<PreparedRecordLoad> {
    let source = match &record.source {
        RecordSource::Blob => PreparedSource::Blob {
            root: store_root.to_path_buf(),
            hash: record.hash.clone(),
        },
        RecordSource::BackingBlob(locator) => PreparedSource::Blob {
            root: locator.store_root.clone(),
            hash: locator.hash.clone(),
        },
        RecordSource::Memory(locator) => {
            let root = memory_roots.get(&locator.memory_id).ok_or_else(|| {
                anyhow::anyhow!("unresolved resident memory: {}", locator.memory_id)
            })?;
            PreparedSource::Memory(native_path(root, &locator.relative_path))
        }
        source => bail!("unsupported resident source kind: {}", source.kind()),
    };
    Ok(PreparedRecordLoad {
        expected_hash: record.hash.clone(),
        source,
    })
}

impl PreparedRecordLoad {
    pub(super) fn expected_hash(&self) -> &str {
        &self.expected_hash
    }

    pub(super) fn load_verified(&self) -> Result<VerifiedBlob> {
        let bytes = match &self.source {
            PreparedSource::Blob { root, hash } => Store::read_blob_from(root, hash)?,
            PreparedSource::Memory(path) => std::fs::read(path)
                .with_context(|| format!("read resident memory file {}", path.display()))?,
        };
        VerifiedBlob::verify(bytes.into(), &self.expected_hash)
    }
}
