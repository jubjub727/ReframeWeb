use std::{
    collections::{HashMap, HashSet},
    io::{Cursor, Read},
};

use zip::{CompressionMethod, ZipArchive};

use crate::PackageError;

pub(crate) const COMPONENT_FILE: &str = "store.wasm";
pub(crate) const MANIFEST_FILE: &str = "manifest.pb";
pub(crate) const SCHEMA_FILE: &str = "schema.binpb";
pub(crate) const CATALOG_FILE: &str = "catalog.pb";
const REQUIRED_FILES: [&str; 4] = [COMPONENT_FILE, MANIFEST_FILE, SCHEMA_FILE, CATALOG_FILE];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PackageLimits {
    pub max_archive_bytes: u64,
    pub max_component_bytes: u64,
    pub max_manifest_bytes: u64,
    pub max_schema_bytes: u64,
    pub max_catalog_bytes: u64,
}

impl Default for PackageLimits {
    fn default() -> Self {
        Self {
            max_archive_bytes: 64 * 1024 * 1024,
            max_component_bytes: 32 * 1024 * 1024,
            max_manifest_bytes: 64 * 1024,
            // Leaves one MiB of framing headroom under the default local
            // transport limit for Envelope metadata and the schema hash.
            max_schema_bytes: 7 * 1024 * 1024,
            max_catalog_bytes: 8 * 1024 * 1024,
        }
    }
}

pub(crate) fn read_archive(
    bytes: &[u8],
    limits: PackageLimits,
) -> Result<HashMap<&'static str, Vec<u8>>, PackageError> {
    validate_central_directory(bytes)?;
    let mut archive = ZipArchive::new(Cursor::new(bytes))?;
    if archive.len() != REQUIRED_FILES.len() {
        return Err(PackageError::EntryCount {
            actual: archive.len(),
        });
    }

    let mut files = HashMap::with_capacity(REQUIRED_FILES.len());
    for index in 0..archive.len() {
        let entry = archive.by_index(index)?;
        let Some(name) = canonical_name(entry.name_raw()) else {
            return Err(PackageError::UnexpectedEntry {
                name: String::from_utf8_lossy(entry.name_raw()).into_owned(),
            });
        };
        validate_entry_type(&entry, name)?;
        let limit = entry_limit(name, limits);
        if entry.size() > limit {
            return Err(too_large(name, entry.size(), limit));
        }
        let capacity = usize::try_from(entry.size()).unwrap_or(0);
        let mut contents = Vec::with_capacity(capacity);
        entry
            .take(limit.saturating_add(1))
            .read_to_end(&mut contents)
            .map_err(|source| PackageError::EntryRead { name, source })?;
        let actual = u64::try_from(contents.len()).unwrap_or(u64::MAX);
        if actual > limit {
            return Err(too_large(name, actual, limit));
        }
        if files.insert(name, contents).is_some() {
            return Err(PackageError::DuplicateEntry { name });
        }
    }
    Ok(files)
}

fn validate_central_directory(bytes: &[u8]) -> Result<(), PackageError> {
    let end = find_end_record(bytes)?;
    let entry_count = little_u16(bytes, end + 10)? as usize;
    if entry_count != REQUIRED_FILES.len() {
        return Err(PackageError::EntryCount {
            actual: entry_count,
        });
    }
    let directory_size = little_u32(bytes, end + 12)? as usize;
    let directory_start = little_u32(bytes, end + 16)? as usize;
    if directory_start.checked_add(directory_size) != Some(end) {
        return Err(PackageError::InvalidArchiveStructure {
            reason: "central directory bounds are inconsistent",
        });
    }

    let mut offset = directory_start;
    let mut names = HashSet::with_capacity(REQUIRED_FILES.len());
    for _ in 0..entry_count {
        if bytes.get(offset..offset + 4) != Some(b"PK\x01\x02") {
            return Err(PackageError::InvalidArchiveStructure {
                reason: "invalid central directory entry signature",
            });
        }
        let name_length = little_u16(bytes, offset + 28)? as usize;
        let extra_length = little_u16(bytes, offset + 30)? as usize;
        let comment_length = little_u16(bytes, offset + 32)? as usize;
        let name_start = offset.checked_add(46).ok_or(structure_error())?;
        let name_end = name_start
            .checked_add(name_length)
            .ok_or(structure_error())?;
        let raw_name = bytes.get(name_start..name_end).ok_or(structure_error())?;
        let Some(name) = canonical_name(raw_name) else {
            return Err(PackageError::UnexpectedEntry {
                name: String::from_utf8_lossy(raw_name).into_owned(),
            });
        };
        if !names.insert(name) {
            return Err(PackageError::DuplicateEntry { name });
        }
        offset = name_end
            .checked_add(extra_length)
            .and_then(|next| next.checked_add(comment_length))
            .ok_or(structure_error())?;
        if offset > end {
            return Err(structure_error());
        }
    }
    if offset != end {
        return Err(structure_error());
    }
    Ok(())
}

fn find_end_record(bytes: &[u8]) -> Result<usize, PackageError> {
    const END_SIZE: usize = 22;
    const MAX_COMMENT: usize = u16::MAX as usize;
    let start = bytes.len().saturating_sub(END_SIZE + MAX_COMMENT);
    for offset in (start..bytes.len().saturating_sub(END_SIZE - 1)).rev() {
        if bytes.get(offset..offset + 4) != Some(b"PK\x05\x06") {
            continue;
        }
        let comment_length = little_u16(bytes, offset + 20)? as usize;
        if offset + END_SIZE + comment_length != bytes.len() {
            continue;
        }
        let disk = little_u16(bytes, offset + 4)?;
        let directory_disk = little_u16(bytes, offset + 6)?;
        let entries_on_disk = little_u16(bytes, offset + 8)?;
        let total_entries = little_u16(bytes, offset + 10)?;
        if disk != 0 || directory_disk != 0 || entries_on_disk != total_entries {
            return Err(PackageError::InvalidArchiveStructure {
                reason: "multi-disk ZIP archives are not supported",
            });
        }
        if total_entries == u16::MAX
            || little_u32(bytes, offset + 12)? == u32::MAX
            || little_u32(bytes, offset + 16)? == u32::MAX
        {
            return Err(PackageError::InvalidArchiveStructure {
                reason: "ZIP64 is unnecessary for bounded Store packages",
            });
        }
        return Ok(offset);
    }
    Err(PackageError::InvalidArchiveStructure {
        reason: "end-of-central-directory record is missing or has trailing data",
    })
}

fn little_u16(bytes: &[u8], offset: usize) -> Result<u16, PackageError> {
    let value: [u8; 2] = bytes
        .get(offset..offset + 2)
        .and_then(|slice| slice.try_into().ok())
        .ok_or(structure_error())?;
    Ok(u16::from_le_bytes(value))
}

fn little_u32(bytes: &[u8], offset: usize) -> Result<u32, PackageError> {
    let value: [u8; 4] = bytes
        .get(offset..offset + 4)
        .and_then(|slice| slice.try_into().ok())
        .ok_or(structure_error())?;
    Ok(u32::from_le_bytes(value))
}

const fn structure_error() -> PackageError {
    PackageError::InvalidArchiveStructure {
        reason: "central directory entry exceeds its declared bounds",
    }
}

fn validate_entry_type<R: Read>(
    entry: &zip::read::ZipFile<'_, R>,
    name: &'static str,
) -> Result<(), PackageError> {
    if entry.is_dir()
        || entry.is_symlink()
        || entry.unix_mode().is_some_and(|mode| {
            let file_type = mode & 0o170_000;
            file_type != 0 && file_type != 0o100_000
        })
    {
        return Err(PackageError::NonRegularEntry {
            name: name.to_owned(),
        });
    }
    if !matches!(
        entry.compression(),
        CompressionMethod::Stored | CompressionMethod::Deflated
    ) {
        return Err(PackageError::UnsupportedCompression {
            name: name.to_owned(),
            method: format!("{:?}", entry.compression()),
        });
    }
    Ok(())
}

fn canonical_name(raw_name: &[u8]) -> Option<&'static str> {
    REQUIRED_FILES
        .into_iter()
        .find(|candidate| candidate.as_bytes() == raw_name)
}

fn entry_limit(name: &'static str, limits: PackageLimits) -> u64 {
    match name {
        COMPONENT_FILE => limits.max_component_bytes,
        MANIFEST_FILE => limits.max_manifest_bytes,
        SCHEMA_FILE => limits.max_schema_bytes,
        CATALOG_FILE => limits.max_catalog_bytes,
        _ => 0,
    }
}

fn too_large(name: &'static str, actual: u64, limit: u64) -> PackageError {
    PackageError::EntryTooLarge {
        name,
        actual,
        limit,
    }
}
