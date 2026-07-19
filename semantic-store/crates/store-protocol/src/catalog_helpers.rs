use crate::package::{CapabilityKind, CatalogEntry, catalog_entry};

impl CatalogEntry {
    #[must_use]
    pub const fn capability_kind(&self) -> CapabilityKind {
        match self.kind {
            Some(catalog_entry::Kind::Topic(_)) => CapabilityKind::Topic,
            Some(catalog_entry::Kind::Resource(_)) => CapabilityKind::Resource,
            Some(catalog_entry::Kind::Function(_)) => CapabilityKind::Function,
            Some(catalog_entry::Kind::Workflow(_)) => CapabilityKind::Workflow,
            None => CapabilityKind::Unspecified,
        }
    }
}
