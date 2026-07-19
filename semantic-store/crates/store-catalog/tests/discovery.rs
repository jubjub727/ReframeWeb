mod support;

use prost::Message;
use reframe_store_catalog::{CatalogError, DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT};
use reframe_store_protocol::{
    package::CapabilityKind,
    wire::{BrowseCatalogRequest, GetStoreCardRequest, SearchCatalogRequest},
};

use support::service;

#[test]
fn store_card_is_minimal_and_search_never_leaks_hidden_intents() {
    let service = service();
    let card = service
        .get_store_card(&GetStoreCardRequest {})
        .expect("store card");
    assert_eq!(card.overview_sentences.len(), 2);
    assert_eq!(card.top_level_topics.len(), 1);
    assert_eq!(card.top_level_topics[0].id, "calendar");

    let response = service
        .search_catalog(&SearchCatalogRequest {
            query: "ultraviolet hidden phrase".to_owned(),
            ..Default::default()
        })
        .expect("hidden intent is indexed");
    assert_eq!(response.hits[0].id, "events.list");
    let wire = String::from_utf8_lossy(&response.encode_to_vec()).into_owned();
    assert!(!wire.contains("ultraviolet"));
    assert!(!wire.contains("hidden phrase"));
}

#[test]
fn search_is_deterministic_weighted_filtered_and_limited() {
    let service = service();
    let request = SearchCatalogRequest {
        query: "common".to_owned(),
        ..Default::default()
    };
    let first = service.search_catalog(&request).expect("first search");
    let second = service.search_catalog(&request).expect("second search");
    assert_eq!(first, second);
    assert_eq!(first.hits.len(), DEFAULT_PAGE_LIMIT);
    assert_eq!(first.hits[0].id, "common-00");

    let capped = service
        .search_catalog(&SearchCatalogRequest {
            query: "common".to_owned(),
            limit: u32::MAX,
            ..Default::default()
        })
        .expect("capped search");
    assert_eq!(capped.hits.len(), MAX_PAGE_LIMIT);

    let filtered = service
        .search_catalog(&SearchCatalogRequest {
            kinds: vec![CapabilityKind::Function as i32],
            topic_id: "events".to_owned(),
            limit: 10,
            ..Default::default()
        })
        .expect("subtree search");
    assert_eq!(filtered.hits.len(), 10);
    assert!(
        filtered
            .hits
            .iter()
            .all(|hit| { hit.kind == CapabilityKind::Function as i32 && hit.id != "events" })
    );
    let including_root = service
        .search_catalog(&SearchCatalogRequest {
            query: "calendar".to_owned(),
            topic_id: "calendar".to_owned(),
            ..Default::default()
        })
        .expect("rooted subtree");
    assert!(including_root.hits.iter().any(|hit| hit.id == "calendar"));
}

#[test]
fn browse_returns_immediate_children_and_authenticated_pages() {
    let service = service();
    let root = service
        .browse_catalog(&BrowseCatalogRequest::default())
        .expect("root browse");
    assert_eq!(
        root.entries
            .iter()
            .map(|entry| entry.id.as_str())
            .collect::<Vec<_>>(),
        ["calendar"]
    );

    let first = service
        .browse_catalog(&BrowseCatalogRequest {
            parent_topic_id: "events".to_owned(),
            limit: 2,
            ..Default::default()
        })
        .expect("first page");
    assert_eq!(first.entries.len(), 2);
    assert!(!first.next_cursor.is_empty());
    let second = service
        .browse_catalog(&BrowseCatalogRequest {
            parent_topic_id: "events".to_owned(),
            limit: 2,
            cursor: first.next_cursor.clone(),
            ..Default::default()
        })
        .expect("second page");
    assert_ne!(first.entries, second.entries);

    let rebound = service.browse_catalog(&BrowseCatalogRequest {
        parent_topic_id: "events".to_owned(),
        kinds: vec![CapabilityKind::Function as i32],
        cursor: first.next_cursor.clone(),
        ..Default::default()
    });
    assert_eq!(rebound, Err(CatalogError::InvalidCursor));

    let mut tampered = first.next_cursor.into_bytes();
    tampered[10] = if tampered[10] == b'A' { b'B' } else { b'A' };
    let tampered = service.browse_catalog(&BrowseCatalogRequest {
        parent_topic_id: "events".to_owned(),
        cursor: String::from_utf8(tampered).expect("ASCII cursor"),
        ..Default::default()
    });
    assert_eq!(tampered, Err(CatalogError::InvalidCursor));
}

#[test]
fn list_budget_never_returns_a_partial_hit() {
    let service = service();
    let first = service
        .search_catalog(&SearchCatalogRequest {
            query: "ultraviolet".to_owned(),
            limit: 1,
            ..Default::default()
        })
        .expect("one hit");
    let exact = first.hits[0].encoded_len();
    let too_small = service.search_catalog(&SearchCatalogRequest {
        query: "ultraviolet".to_owned(),
        byte_budget: u32::try_from(exact - 1).expect("small hit"),
        ..Default::default()
    });
    assert_eq!(
        too_small,
        Err(CatalogError::BudgetExceeded {
            budget: exact - 1,
            required: exact,
        })
    );
    let exact_page = service
        .search_catalog(&SearchCatalogRequest {
            query: "ultraviolet".to_owned(),
            byte_budget: u32::try_from(exact).expect("small hit"),
            ..Default::default()
        })
        .expect("exact complete-hit budget");
    assert_eq!(exact_page.hits.len(), 1);
}
