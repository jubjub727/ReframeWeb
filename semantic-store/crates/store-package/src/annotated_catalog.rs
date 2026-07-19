mod drift;
mod extract;

use std::collections::{BTreeMap, HashSet};

use prost_reflect::DescriptorPool;
use reframe_store_protocol::package::{Catalog, CatalogEntry, Example, catalog_entry};

use crate::{CatalogError, catalog_validation::validate_generated_catalog};

/// Store-card metadata and the catalog content that cannot come from RPC annotations.
///
/// Entries are intentionally limited to topics and workflows. Resource and function
/// entries are derived from method annotations, while examples are merged by stable
/// capability ID and reflectively type-checked during generation and package loading.
#[derive(Debug, Clone, Default)]
pub struct AuthoredCatalog {
    pub store_id: String,
    pub display_name: String,
    pub overview_sentences: [String; 2],
    pub entries: Vec<CatalogEntry>,
    pub examples_by_capability: BTreeMap<String, Vec<Example>>,
}

/// Generates a deterministic catalog directly from original descriptor-set bytes.
///
/// Decoding the original bytes is required to preserve protobuf custom options.
pub fn generate_catalog(
    raw_schema_bytes: &[u8],
    authored: AuthoredCatalog,
) -> Result<Catalog, CatalogError> {
    let pool = DescriptorPool::decode(raw_schema_bytes).map_err(|error| {
        CatalogError::InvalidAnnotatedSchema {
            reason: error.to_string(),
        }
    })?;
    reframe_store_protocol::validate_store_id(&authored.store_id).map_err(|_| {
        CatalogError::InvalidAuthoredStoreId {
            store_id: authored.store_id.clone(),
        }
    })?;
    let mut entries = extract::capabilities(&pool, &authored.store_id)?
        .ok_or(CatalogError::MissingCapabilityExtension)?;
    validate_authored_kinds(&authored.entries)?;
    entries.extend(authored.entries);
    reject_duplicate_ids(&entries)?;
    attach_examples(&mut entries, authored.examples_by_capability)?;
    entries.sort_unstable_by(|left, right| left.id.cmp(&right.id));

    let top_level_topic_ids = entries
        .iter()
        .filter(|entry| {
            entry.parent_topic_id.is_empty()
                && matches!(entry.kind, Some(catalog_entry::Kind::Topic(_)))
        })
        .map(|entry| entry.id.clone())
        .collect();
    let catalog = Catalog {
        format_version: crate::catalog_validation::CATALOG_FORMAT_VERSION,
        store_id: authored.store_id,
        display_name: authored.display_name,
        overview_sentences: authored.overview_sentences.into(),
        top_level_topic_ids,
        entries,
        ..Catalog::default()
    };
    validate_generated_catalog(&catalog, &pool)?;
    Ok(catalog)
}

/// Reports whether the original descriptor bytes declare a Store service for `store_id`.
///
/// Invalid or partially annotated schemas are rejected rather than treated as legacy.
pub fn schema_uses_annotations(
    raw_schema_bytes: &[u8],
    store_id: &str,
) -> Result<bool, CatalogError> {
    reframe_store_protocol::validate_store_id(store_id).map_err(|_| {
        CatalogError::InvalidAuthoredStoreId {
            store_id: store_id.to_owned(),
        }
    })?;
    let pool = DescriptorPool::decode(raw_schema_bytes).map_err(|error| {
        CatalogError::InvalidAnnotatedSchema {
            reason: error.to_string(),
        }
    })?;
    Ok(extract::capabilities(&pool, store_id)?.is_some())
}

pub(crate) use drift::validate as validate_drift;

fn validate_authored_kinds(entries: &[CatalogEntry]) -> Result<(), CatalogError> {
    for entry in entries {
        if !matches!(
            entry.kind,
            Some(catalog_entry::Kind::Topic(_)) | Some(catalog_entry::Kind::Workflow(_))
        ) {
            return Err(CatalogError::InvalidAuthoredEntryKind {
                entry_id: entry.id.clone(),
            });
        }
    }
    Ok(())
}

fn reject_duplicate_ids(entries: &[CatalogEntry]) -> Result<(), CatalogError> {
    let mut ids = HashSet::with_capacity(entries.len());
    for entry in entries {
        if !ids.insert(entry.id.as_str()) {
            return Err(CatalogError::DuplicateEntry {
                entry_id: entry.id.clone(),
            });
        }
    }
    Ok(())
}

fn attach_examples(
    entries: &mut [CatalogEntry],
    examples_by_capability: BTreeMap<String, Vec<Example>>,
) -> Result<(), CatalogError> {
    for (entry_id, examples) in examples_by_capability {
        let Some(entry) = entries.iter_mut().find(|entry| entry.id == entry_id) else {
            return Err(CatalogError::UnknownExampleTarget { entry_id });
        };
        if matches!(entry.kind, Some(catalog_entry::Kind::Topic(_))) {
            return Err(CatalogError::ExamplesTargetTopic { entry_id });
        }
        entry
            .guidance
            .as_mut()
            .ok_or_else(|| CatalogError::MissingGuidance {
                entry_id: entry.id.clone(),
            })?
            .examples
            .extend(examples);
    }
    Ok(())
}
