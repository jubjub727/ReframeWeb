use std::sync::Arc;

use prost_reflect::DescriptorPool;
use reframe_store_catalog::{CatalogError, CatalogService};
use reframe_store_protocol::{
    package::{Catalog, CatalogEntry, Topic, catalog_entry},
    wire::SearchCatalogRequest,
};

use crate::{EngineConfig, RuntimeEngine};

use super::StoreRegistry;

#[tokio::test]
async fn cancelled_compilation_waiters_release_their_single_flight_cell() {
    let engine = Arc::new(RuntimeEngine::new(EngineConfig::default()).expect("engine"));
    let registry = Arc::new(StoreRegistry::new(engine));
    let task_registry = Arc::clone(&registry);
    let (acquired, acquired_rx) = tokio::sync::oneshot::channel();

    let task = tokio::spawn(async move {
        let _lease = super::CompilationLease {
            cell: Arc::clone(
                task_registry
                    .compilations
                    .entry([7; 32])
                    .or_insert_with(|| Arc::new(tokio::sync::OnceCell::new()))
                    .value(),
            ),
            hash: [7; 32],
            map: &task_registry.compilations,
        };
        acquired.send(()).expect("acquisition signal");
        std::future::pending::<()>().await;
    });

    acquired_rx.await.expect("lease acquired");
    assert_eq!(registry.compilations.len(), 1);
    task.abort();
    assert!(task.await.unwrap_err().is_cancelled());
    assert!(registry.compilations.is_empty());
}

#[tokio::test]
async fn cursor_authorities_are_stable_per_store_and_isolated_between_stores() {
    let engine = Arc::new(RuntimeEngine::new(EngineConfig::default()).expect("engine"));
    let registry = StoreRegistry::new(engine);
    let old = service(registry.cursor_authority("dev.reframe.one"), [1; 32]);
    let updated = service(registry.cursor_authority("dev.reframe.one"), [2; 32]);
    let foreign = service(registry.cursor_authority("dev.reframe.two"), [2; 32]);

    let first_page = old.search_catalog(&request(String::new())).expect("page");
    assert!(!first_page.next_cursor.is_empty());
    let continued = request(first_page.next_cursor);

    assert!(matches!(
        updated.search_catalog(&continued),
        Err(CatalogError::StaleCursor)
    ));
    assert!(matches!(
        foreign.search_catalog(&continued),
        Err(CatalogError::InvalidCursor)
    ));
}

fn service(
    authority: reframe_store_catalog::CursorAuthority,
    revision: [u8; 32],
) -> CatalogService {
    let entries = (0..2)
        .map(|index| CatalogEntry {
            id: format!("topic.{index}"),
            title: format!("Topic {index}"),
            summary: format!("Catalog topic {index}."),
            kind: Some(catalog_entry::Kind::Topic(Topic {})),
            ..CatalogEntry::default()
        })
        .collect();
    CatalogService::with_cursor_authority(
        Catalog {
            entries,
            ..Catalog::default()
        },
        DescriptorPool::new(),
        Arc::from([]),
        revision,
        authority,
    )
    .expect("catalog service")
}

fn request(cursor: String) -> SearchCatalogRequest {
    SearchCatalogRequest {
        limit: 1,
        cursor,
        ..SearchCatalogRequest::default()
    }
}
