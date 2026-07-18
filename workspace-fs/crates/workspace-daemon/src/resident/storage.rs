use anyhow::{Result, bail};

use crate::model::{FileRecord, RecordSource};
use crate::paths::native_path;
use crate::store::Store;

pub(super) fn load_record(store: &Store, record: &FileRecord) -> Result<Vec<u8>> {
    match &record.source {
        RecordSource::Blob => store.read_blob(&record.hash),
        RecordSource::BackingBlob(locator) => {
            Store::open(&locator.store_root)?.read_blob(&locator.hash)
        }
        RecordSource::Memory(locator) => std::fs::read(native_path(
            &store.memory_path(&locator.memory_id)?,
            &locator.relative_path,
        ))
        .map_err(Into::into),
        source => bail!("unsupported resident source kind: {}", source.kind()),
    }
}

pub(super) fn validate_content(record: &FileRecord, bytes: &[u8]) -> Result<()> {
    let actual = blake3::hash(bytes).to_hex().to_string();
    if actual != record.hash {
        bail!(
            "filesystem memory changed after session creation at {} (expected {}, found {})",
            record.path,
            record.hash,
            actual
        );
    }
    Ok(())
}
