mod descriptors;
mod metadata;
mod relationships;

use std::collections::HashMap;

use prost_reflect::DescriptorPool;
use reframe_store_protocol::package::{Catalog, CatalogEntry};
use thiserror::Error;

pub const CATALOG_FORMAT_VERSION: u32 = 1;
pub(crate) type EntryMap<'a> = HashMap<&'a str, &'a CatalogEntry>;

#[derive(Debug, Clone, PartialEq, Eq, Error)]
#[non_exhaustive]
pub enum CatalogError {
    #[error("catalog format version {found} is unsupported")]
    UnsupportedFormat { found: u32 },
    #[error("catalog Store ID does not match manifest")]
    StoreIdMismatch,
    #[error("catalog interface version does not match manifest")]
    InterfaceVersionMismatch,
    #[error("catalog field {field:?} is missing, invalid, or exceeds its bound")]
    InvalidMetadata { field: &'static str },
    #[error("catalog entry {entry_id:?} has an invalid {field}")]
    InvalidEntry {
        entry_id: String,
        field: &'static str,
    },
    #[error("catalog entry {entry_id:?} exceeds the {limit} item bound for {field}")]
    MetadataLimit {
        entry_id: String,
        field: &'static str,
        limit: usize,
    },
    #[error("catalog contains duplicate entry ID {entry_id:?}")]
    DuplicateEntry { entry_id: String },
    #[error("catalog entry {entry_id:?} does not declare a kind")]
    MissingKind { entry_id: String },
    #[error("entry {entry_id:?} references missing {relation} {target_id:?}")]
    MissingRelation {
        entry_id: String,
        relation: &'static str,
        target_id: String,
    },
    #[error("entry {entry_id:?} has non-topic parent {parent_id:?}")]
    ParentNotTopic { entry_id: String, parent_id: String },
    #[error("topic parent cycle includes {entry_id:?}")]
    ParentCycle { entry_id: String },
    #[error("entry {entry_id:?} repeats {relation} {target_id:?}")]
    DuplicateRelation {
        entry_id: String,
        relation: &'static str,
        target_id: String,
    },
    #[error("entry {entry_id:?} relates to itself")]
    SelfRelation { entry_id: String },
    #[error("top-level topic list contains invalid entry {entry_id:?}")]
    InvalidTopLevelTopic { entry_id: String },
    #[error("top-level topic list omits root topic {entry_id:?}")]
    MissingTopLevelTopic { entry_id: String },
    #[error("capability {entry_id:?} has missing or effectively empty guidance")]
    MissingGuidance { entry_id: String },
    #[error("capability {entry_id:?} has incomplete method binding")]
    InvalidMethodBinding { entry_id: String },
    #[error("capability {entry_id:?} references missing service {service:?}")]
    ServiceNotFound { entry_id: String, service: String },
    #[error("capability {entry_id:?} references missing method {service}.{method}")]
    MethodNotFound {
        entry_id: String,
        service: String,
        method: String,
    },
    #[error("method {service}.{method} is bound by more than one capability")]
    DuplicateMethodBinding { service: String, method: String },
    #[error(
        "capability {entry_id:?} declares {direction} type {declared:?}, but its method uses {actual:?}"
    )]
    MethodTypeMismatch {
        entry_id: String,
        direction: &'static str,
        declared: String,
        actual: String,
    },
    #[error("function {entry_id:?} must explicitly declare side effects and idempotency")]
    IncompleteFunctionMetadata { entry_id: String },
    #[error("protobuf method {service}.{method} bound by {entry_id:?} must be unary")]
    StreamingMethodBinding {
        entry_id: String,
        service: String,
        method: String,
    },
    #[error("schema.binpb cannot be decoded for annotated catalog generation: {reason}")]
    InvalidAnnotatedSchema { reason: String },
    #[error("schema.binpb does not define the canonical Semantic Store capability option")]
    MissingCapabilityExtension,
    #[error("authored catalog has an invalid Store ID: {store_id:?}")]
    InvalidAuthoredStoreId { store_id: String },
    #[error("schema.binpb has no Store service marked for Store ID {store_id:?}")]
    MissingAnnotatedStoreService { store_id: String },
    #[error("Store service for {store_id:?} has no annotated capability methods")]
    MissingAnnotatedCapabilities { store_id: String },
    #[error("capability option on method {method:?} is invalid: {reason}")]
    InvalidCapabilityAnnotation { method: String, reason: String },
    #[error("Store service option on {service:?} is invalid: {reason}")]
    InvalidStoreServiceAnnotation { service: String, reason: String },
    #[error("annotated method {method:?} does not declare a capability kind")]
    MissingCapabilityKind { method: String },
    #[error("method {method:?} on a marked Store service has no capability annotation")]
    MissingMethodCapabilityAnnotation { method: String },
    #[error("authored catalog entry {entry_id:?} must be a Topic or Workflow")]
    InvalidAuthoredEntryKind { entry_id: String },
    #[error("typed examples target unknown capability {entry_id:?}")]
    UnknownExampleTarget { entry_id: String },
    #[error("typed examples cannot target topic {entry_id:?}")]
    ExamplesTargetTopic { entry_id: String },
    #[error("catalog omits annotated capability {entry_id:?}")]
    MissingAnnotatedCapability { entry_id: String },
    #[error("catalog capability {entry_id:?} has no canonical method annotation")]
    UnannotatedCapability { entry_id: String },
    #[error("catalog capability {entry_id:?} drifted from annotation field {field}")]
    AnnotationDrift {
        entry_id: String,
        field: &'static str,
    },
    #[error("workflow {entry_id:?} has no steps")]
    EmptyWorkflow { entry_id: String },
    #[error("example {index} on {entry_id:?} is missing its {direction} Any value")]
    MissingExampleValue {
        entry_id: String,
        index: usize,
        direction: &'static str,
    },
    #[error(
        "example {index} on {entry_id:?} has {direction} type {actual:?}; expected {expected:?}"
    )]
    ExampleTypeMismatch {
        entry_id: String,
        index: usize,
        direction: &'static str,
        expected: String,
        actual: String,
    },
    #[error("example {index} on {entry_id:?} has unknown {direction} type {type_name:?}")]
    UnknownExampleType {
        entry_id: String,
        index: usize,
        direction: &'static str,
        type_name: String,
    },
    #[error("example {index} on {entry_id:?} has an invalid protobuf {direction} payload")]
    InvalidExamplePayload {
        entry_id: String,
        index: usize,
        direction: &'static str,
    },
}

pub(crate) fn validate_catalog(
    catalog: &Catalog,
    manifest_store_id: &str,
    manifest_interface: &reframe_store_protocol::package::InterfaceVersion,
    pool: &DescriptorPool,
) -> Result<(), CatalogError> {
    metadata::validate_header(catalog, manifest_store_id, manifest_interface)?;
    validate_entries(catalog, pool)?;
    crate::annotated_catalog::validate_drift(catalog, pool, manifest_store_id)
}

pub(crate) fn validate_entries(
    catalog: &Catalog,
    pool: &DescriptorPool,
) -> Result<(), CatalogError> {
    let mut entries = HashMap::with_capacity(catalog.entries.len());
    for entry in &catalog.entries {
        metadata::validate_entry(entry)?;
        if entries.insert(entry.id.as_str(), entry).is_some() {
            return Err(CatalogError::DuplicateEntry {
                entry_id: entry.id.clone(),
            });
        }
    }
    relationships::validate(catalog, &entries)?;
    descriptors::validate(&entries, pool)
}

pub(crate) fn validate_generated_catalog(
    catalog: &Catalog,
    pool: &DescriptorPool,
) -> Result<(), CatalogError> {
    metadata::validate_store_card(catalog)?;
    validate_entries(catalog, pool)
}

pub(crate) fn invalid_entry(entry: &CatalogEntry, field: &'static str) -> CatalogError {
    CatalogError::InvalidEntry {
        entry_id: entry.id.clone(),
        field,
    }
}

pub(crate) fn missing_relation(
    entry: &CatalogEntry,
    relation: &'static str,
    target: &str,
) -> CatalogError {
    CatalogError::MissingRelation {
        entry_id: entry.id.clone(),
        relation,
        target_id: target.to_owned(),
    }
}
