use std::sync::{
    Arc, Weak,
    atomic::{AtomicU64, Ordering},
};

use dashmap::DashMap;
use reframe_store_catalog::{CatalogService, CursorAuthority};
use reframe_store_package::VerifiedPackage;
use thiserror::Error;
use tokio::sync::OnceCell;
use tokio::sync::Semaphore;

use crate::{CompiledComponent, ComponentError, RuntimeEngine};

type CompilationCell = OnceCell<Arc<CompiledComponent>>;
const MAX_CONCURRENT_COMPILATIONS: usize = 2;

struct CompilationLease<'a> {
    cell: Arc<CompilationCell>,
    hash: [u8; 32],
    map: &'a DashMap<[u8; 32], Arc<CompilationCell>>,
}

impl Drop for CompilationLease<'_> {
    fn drop(&mut self) {
        self.map.remove_if(&self.hash, |_, current| {
            Arc::ptr_eq(current, &self.cell) && Arc::strong_count(current) == 2
        });
    }
}

/// One immutable Store revision ready for discovery and execution.
pub struct LoadedStore {
    package: Arc<VerifiedPackage>,
    catalog: Arc<CatalogService>,
    component: Arc<CompiledComponent>,
}

impl std::fmt::Debug for LoadedStore {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("LoadedStore")
            .field("store_id", &self.package.manifest().store_id)
            .field("store_version", self.package.store_version())
            .field("catalog_revision", &self.package.catalog_revision())
            .finish_non_exhaustive()
    }
}

impl LoadedStore {
    #[must_use]
    pub fn package(&self) -> &VerifiedPackage {
        &self.package
    }

    #[must_use]
    pub fn catalog(&self) -> &CatalogService {
        &self.catalog
    }

    #[must_use]
    pub fn component(&self) -> &CompiledComponent {
        &self.component
    }
}

/// Active Store revisions plus a digest-keyed component compilation cache.
pub struct StoreRegistry {
    components: DashMap<[u8; 32], Weak<CompiledComponent>>,
    compilations: DashMap<[u8; 32], Arc<CompilationCell>>,
    compilation_count: AtomicU64,
    compilation_slots: Arc<Semaphore>,
    cursor_authorities: DashMap<String, CursorAuthority>,
    engine: Arc<RuntimeEngine>,
    stores: DashMap<String, Arc<LoadedStore>>,
}

impl std::fmt::Debug for StoreRegistry {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("StoreRegistry")
            .field("stores", &self.stores.len())
            .field("compilations", &self.compilation_count())
            .finish_non_exhaustive()
    }
}

impl StoreRegistry {
    #[must_use]
    pub fn new(engine: Arc<RuntimeEngine>) -> Self {
        Self {
            components: DashMap::new(),
            compilations: DashMap::new(),
            compilation_count: AtomicU64::new(0),
            compilation_slots: Arc::new(Semaphore::new(MAX_CONCURRENT_COMPILATIONS)),
            cursor_authorities: DashMap::new(),
            engine,
            stores: DashMap::new(),
        }
    }

    /// Verifies catalog runtime projections, single-flights compilation by
    /// component digest, reuses components while loaded, and atomically selects
    /// the revision for new sessions. Existing sessions retain their previous
    /// `Arc` snapshot.
    pub async fn register(
        &self,
        package: VerifiedPackage,
    ) -> Result<Option<Arc<LoadedStore>>, RegisterError> {
        let store_id = package.manifest().store_id.clone();
        let cursor_authority = self.cursor_authority(&store_id);
        let catalog = Arc::new(CatalogService::with_cursor_authority(
            package.catalog_arc(),
            package.descriptor_pool().clone(),
            package.schema_bytes_arc(),
            package.catalog_revision(),
            cursor_authority,
        )?);
        let component = self
            .compiled_component(package.component_hash(), package.component_bytes())
            .await?;
        let loaded = Arc::new(LoadedStore {
            package: Arc::new(package),
            catalog,
            component,
        });
        Ok(self.stores.insert(store_id, loaded))
    }

    #[must_use]
    pub fn get(&self, store_id: &str) -> Option<Arc<LoadedStore>> {
        self.stores
            .get(store_id)
            .map(|entry| Arc::clone(entry.value()))
    }

    #[must_use]
    pub fn list(&self) -> Vec<Arc<LoadedStore>> {
        let mut stores: Vec<_> = self
            .stores
            .iter()
            .map(|entry| Arc::clone(entry.value()))
            .collect();
        stores.sort_unstable_by(|left, right| {
            left.package
                .manifest()
                .store_id
                .cmp(&right.package.manifest().store_id)
        });
        stores
    }

    #[must_use]
    pub fn compilation_count(&self) -> u64 {
        self.compilation_count.load(Ordering::Relaxed)
    }

    fn cursor_authority(&self, store_id: &str) -> CursorAuthority {
        self.cursor_authorities
            .entry(store_id.to_owned())
            .or_default()
            .clone()
    }

    async fn compiled_component(
        &self,
        hash: [u8; 32],
        bytes: &[u8],
    ) -> Result<Arc<CompiledComponent>, RegisterError> {
        self.components
            .retain(|_, component| component.strong_count() > 0);
        if let Some(component) = self
            .components
            .get(&hash)
            .and_then(|component| component.upgrade())
        {
            return Ok(component);
        }

        let lease = CompilationLease {
            cell: Arc::clone(
                self.compilations
                    .entry(hash)
                    .or_insert_with(|| Arc::new(OnceCell::new()))
                    .value(),
            ),
            hash,
            map: &self.compilations,
        };
        let result = lease
            .cell
            .get_or_try_init(|| async {
                if let Some(component) = self
                    .components
                    .get(&hash)
                    .and_then(|component| component.upgrade())
                {
                    return Ok(component);
                }
                let permit = Arc::clone(&self.compilation_slots)
                    .acquire_owned()
                    .await
                    .expect("the registry never closes its compilation semaphore");
                let engine = Arc::clone(&self.engine);
                let bytes: Arc<[u8]> = Arc::from(bytes);
                let component = tokio::task::spawn_blocking(move || {
                    let _permit = permit;
                    CompiledComponent::compile(engine, bytes.as_ref())
                })
                .await
                .map_err(RegisterError::CompileTask)??;
                self.compilation_count.fetch_add(1, Ordering::Relaxed);
                Ok::<_, RegisterError>(Arc::new(component))
            })
            .await
            .map(Arc::clone);
        if let Ok(component) = &result {
            self.components.insert(hash, Arc::downgrade(component));
        }
        result
    }
}

#[cfg(test)]
mod tests;

#[derive(Debug, Error)]
#[non_exhaustive]
pub enum RegisterError {
    #[error("invalid runtime catalog: {0}")]
    Catalog(#[from] reframe_store_catalog::CatalogError),
    #[error(transparent)]
    Component(#[from] ComponentError),
    #[error("component compiler task failed")]
    CompileTask(#[source] tokio::task::JoinError),
}
