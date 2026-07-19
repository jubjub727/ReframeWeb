use std::io;

use thiserror::Error;

use crate::CatalogError;

#[derive(Debug, Error)]
#[non_exhaustive]
pub enum PackageError {
    #[error("archive is {actual} bytes; the configured limit is {limit} bytes")]
    ArchiveTooLarge { actual: u64, limit: u64 },
    #[error("invalid ZIP archive: {0}")]
    Zip(#[from] zip::result::ZipError),
    #[error("invalid or unsupported ZIP structure: {reason}")]
    InvalidArchiveStructure { reason: &'static str },
    #[error("archive contains {actual} entries; exactly four are required")]
    EntryCount { actual: usize },
    #[error("archive contains an unexpected root entry: {name:?}")]
    UnexpectedEntry { name: String },
    #[error("archive contains duplicate entry {name:?}")]
    DuplicateEntry { name: &'static str },
    #[error("required entry {name:?} is missing")]
    MissingEntry { name: &'static str },
    #[error("entry {name:?} is not a regular root file")]
    NonRegularEntry { name: String },
    #[error("entry {name:?} uses unsupported compression method {method}")]
    UnsupportedCompression { name: String, method: String },
    #[error("entry {name:?} is {actual} bytes; the configured limit is {limit} bytes")]
    EntryTooLarge {
        name: &'static str,
        actual: u64,
        limit: u64,
    },
    #[error("failed to read entry {name:?}: {source}")]
    EntryRead {
        name: &'static str,
        #[source]
        source: io::Error,
    },
    #[error("failed to decode manifest.pb: {0}")]
    ManifestDecode(#[source] prost::DecodeError),
    #[error("manifest has an invalid Store ID: {0}")]
    InvalidStoreId(#[source] reframe_store_protocol::ValidationError),
    #[error("manifest Store release {value:?} is not semantic versioning: {source}")]
    InvalidStoreVersion {
        value: String,
        #[source]
        source: semver::Error,
    },
    #[error("manifest field {field:?} is missing")]
    MissingManifestField { field: &'static str },
    #[error("manifest field {field:?} is invalid: {reason}")]
    InvalidManifestField {
        field: &'static str,
        reason: &'static str,
    },
    #[error("package requires protocol {major}.{minor}, which this host does not support")]
    UnsupportedProtocol { major: u32, minor: u32 },
    #[error("SHA-256 mismatch for exact bytes of {entry:?}")]
    HashMismatch {
        entry: &'static str,
        expected: [u8; 32],
        actual: [u8; 32],
    },
    #[error("failed to decode schema.binpb: {0}")]
    SchemaDecode(#[source] prost::DecodeError),
    #[error("schema.binpb contains no file descriptors")]
    EmptySchema,
    #[error("schema file {file:?} does not contain source information")]
    MissingSourceInfo { file: String },
    #[error("schema.binpb is not a valid closed descriptor set: {0}")]
    InvalidDescriptorSet(#[source] prost_reflect::DescriptorError),
    #[error("failed to decode catalog.pb: {0}")]
    CatalogDecode(#[source] prost::DecodeError),
    #[error("entry {entry:?} failed structural protobuf preflight: {source}")]
    ProtobufShape {
        entry: &'static str,
        #[source]
        source: reframe_store_protocol::PayloadShapeError,
    },
    #[error(transparent)]
    InvalidCatalog(#[from] CatalogError),
    #[error("failed to write package: {0}")]
    Write(#[source] io::Error),
}
