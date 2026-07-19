use std::{
    collections::{BTreeMap, HashMap},
    sync::Arc,
};

use prost_reflect::DescriptorPool;
use reframe_store_protocol::package::{CapabilityKind, Catalog, CatalogEntry, catalog_entry};
use sha2::{Digest, Sha256};

use crate::{
    CatalogError,
    cursor::{CursorAuthority, CursorCodec},
    hierarchy::HierarchyIndex,
    index::SearchIndex,
};

/// Immutable catalog data and its precomputed discovery structures.
pub struct CatalogService {
    pub(crate) catalog: Arc<Catalog>,
    pub(crate) entries: BTreeMap<String, usize>,
    pub(crate) children: HashMap<String, Vec<String>>,
    pub(crate) hierarchy: HierarchyIndex,
    pub(crate) descriptor_pool: DescriptorPool,
    pub(crate) schema_bundle: Arc<[u8]>,
    pub(crate) schema_hash: [u8; 32],
    pub(crate) revision: [u8; 32],
    pub(crate) index: SearchIndex,
    pub(crate) cursor: CursorCodec,
}

impl std::fmt::Debug for CatalogService {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("CatalogService")
            .field("store_id", &self.catalog.store_id)
            .field("entries", &self.entries.len())
            .field("schema_bytes", &self.schema_bundle.len())
            .field("revision", &self.revision)
            .finish_non_exhaustive()
    }
}

impl CatalogService {
    /// Builds a service over verified catalog metadata and the exact packaged
    /// descriptor bytes. The raw schema bytes are retained without reencoding.
    pub fn new(
        catalog: Catalog,
        descriptor_pool: DescriptorPool,
        schema_bundle: Arc<[u8]>,
        catalog_revision: [u8; 32],
    ) -> Result<Self, CatalogError> {
        Self::with_cursor_authority(
            catalog,
            descriptor_pool,
            schema_bundle,
            catalog_revision,
            CursorAuthority::new(),
        )
    }

    /// Builds a service using an existing opaque cursor authority.
    ///
    /// Revisions of one Store ID must share an authority so an authenticated
    /// cursor from an older revision is reported as stale. Authorities must not
    /// be shared between different Store IDs.
    pub fn with_cursor_authority(
        catalog: impl Into<Arc<Catalog>>,
        descriptor_pool: DescriptorPool,
        schema_bundle: Arc<[u8]>,
        catalog_revision: [u8; 32],
        cursor_authority: CursorAuthority,
    ) -> Result<Self, CatalogError> {
        let catalog = catalog.into();
        let mut entries = BTreeMap::new();
        for (entry_index, entry) in catalog.entries.iter().enumerate() {
            if entry.kind.is_none() {
                return Err(CatalogError::InvalidCatalog {
                    reason: "an entry has no capability kind",
                });
            }
            if entries.insert(entry.id.clone(), entry_index).is_some() {
                return Err(CatalogError::InvalidCatalog {
                    reason: "entry IDs are not unique",
                });
            }
        }

        let mut children = HashMap::<String, Vec<String>>::new();
        for entry in &catalog.entries {
            validate_parent(entry, &entries, &catalog)?;
            children
                .entry(entry.parent_topic_id.clone())
                .or_default()
                .push(entry.id.clone());
        }
        for values in children.values_mut() {
            values.sort_unstable();
        }

        for topic_id in &catalog.top_level_topic_ids {
            let Some(entry_index) = entries.get(topic_id) else {
                return Err(CatalogError::InvalidCatalog {
                    reason: "a top-level topic is missing",
                });
            };
            let entry = &catalog.entries[*entry_index];
            if entry_kind(entry)? != CapabilityKind::Topic || !entry.parent_topic_id.is_empty() {
                return Err(CatalogError::InvalidCatalog {
                    reason: "a top-level topic declaration is invalid",
                });
            }
        }

        let hierarchy = HierarchyIndex::build(&entries, &catalog, &children)?;
        let index = SearchIndex::build(catalog.entries.iter());
        let schema_hash = Sha256::digest(&schema_bundle).into();
        Ok(Self {
            catalog,
            entries,
            children,
            hierarchy,
            descriptor_pool,
            schema_bundle,
            schema_hash,
            revision: catalog_revision,
            index,
            cursor: CursorCodec::with_authority(cursor_authority),
        })
    }

    /// Exact catalog artifact revision used for caches and cursors.
    #[must_use]
    pub const fn catalog_revision(&self) -> [u8; 32] {
        self.revision
    }

    /// SHA-256 of the exact packaged descriptor-set bytes.
    #[must_use]
    pub const fn schema_artifact_hash(&self) -> [u8; 32] {
        self.schema_hash
    }

    pub(crate) fn entry(&self, id: &str) -> Result<&CatalogEntry, CatalogError> {
        self.entries
            .get(id)
            .and_then(|index| self.catalog.entries.get(*index))
            .ok_or_else(|| CatalogError::CapabilityNotFound {
                capability_id: id.to_owned(),
            })
    }
}

pub(crate) fn entry_kind(entry: &CatalogEntry) -> Result<CapabilityKind, CatalogError> {
    match entry.kind {
        Some(catalog_entry::Kind::Topic(_)) => Ok(CapabilityKind::Topic),
        Some(catalog_entry::Kind::Resource(_)) => Ok(CapabilityKind::Resource),
        Some(catalog_entry::Kind::Function(_)) => Ok(CapabilityKind::Function),
        Some(catalog_entry::Kind::Workflow(_)) => Ok(CapabilityKind::Workflow),
        None => Err(CatalogError::InvalidCatalog {
            reason: "an entry has no capability kind",
        }),
    }
}

fn validate_parent(
    entry: &CatalogEntry,
    entries: &BTreeMap<String, usize>,
    catalog: &Catalog,
) -> Result<(), CatalogError> {
    if entry.parent_topic_id.is_empty() {
        return Ok(());
    }
    let Some(parent_index) = entries.get(&entry.parent_topic_id) else {
        return Err(CatalogError::InvalidCatalog {
            reason: "an entry references a missing parent topic",
        });
    };
    let parent = &catalog.entries[*parent_index];
    if entry_kind(parent)? != CapabilityKind::Topic {
        return Err(CatalogError::InvalidCatalog {
            reason: "an entry parent is not a topic",
        });
    }
    Ok(())
}
