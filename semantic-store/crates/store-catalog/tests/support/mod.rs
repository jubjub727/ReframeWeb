#![allow(dead_code)]

use std::sync::Arc;

use prost::Message;
use prost_reflect::DescriptorPool;
use prost_types::Any;
use reframe_store_catalog::CatalogService;
use reframe_store_protocol::{
    package::{
        CapabilityKind, Catalog, CatalogEntry, Example, Function, Guidance, Idempotency,
        InterfaceVersion, Resource, SideEffect, Topic, Workflow, WorkflowStep, catalog_entry,
    },
    wire::{CatalogHit, GetStoreCardRequest},
};

pub const REVISION: [u8; 32] = [9; 32];
pub const HIT_TYPE: &str = "reframe.semantic_store.v1.CatalogHit";
pub const EMPTY_TYPE: &str = "reframe.semantic_store.v1.GetStoreCardRequest";

pub fn service() -> CatalogService {
    service_from_catalog(sample_catalog())
}

pub fn service_from_catalog(catalog: Catalog) -> CatalogService {
    let schema = reframe_store_protocol::descriptor_set_bytes();
    let pool = DescriptorPool::decode(schema).expect("protocol descriptor set");
    CatalogService::new(catalog, pool, Arc::from(schema), REVISION).expect("valid test catalog")
}

pub fn sample_catalog() -> Catalog {
    let mut entries = vec![
        topic("calendar", "Calendar", "Calendar capabilities", ""),
        topic("events", "Events", "Event capabilities", "calendar"),
        resource(),
        function("events.create", "Create event", "Create one calendar event"),
        workflow(),
    ];
    for index in 0..12 {
        entries.push(function(
            &format!("common-{index:02}"),
            "Common action",
            "A common calendar action",
        ));
    }
    Catalog {
        format_version: 1,
        store_id: "test.store".to_owned(),
        semantic_interface_version: Some(InterfaceVersion { major: 1, minor: 0 }),
        display_name: "Test Store".to_owned(),
        overview_sentences: vec![
            "First overview sentence.".to_owned(),
            "Second sentence.".to_owned(),
        ],
        top_level_topic_ids: vec!["calendar".to_owned()],
        entries,
    }
}

pub fn empty_catalog() -> Catalog {
    Catalog {
        format_version: 1,
        store_id: "test.types".to_owned(),
        semantic_interface_version: Some(InterfaceVersion { major: 1, minor: 0 }),
        display_name: "Types".to_owned(),
        overview_sentences: vec!["One.".to_owned(), "Two.".to_owned()],
        top_level_topic_ids: vec!["root".to_owned()],
        entries: vec![topic("root", "Root", "Root topic", "")],
    }
}

fn topic(id: &str, title: &str, summary: &str, parent: &str) -> CatalogEntry {
    CatalogEntry {
        id: id.to_owned(),
        parent_topic_id: parent.to_owned(),
        title: title.to_owned(),
        summary: summary.to_owned(),
        kind: Some(catalog_entry::Kind::Topic(Topic {})),
        ..Default::default()
    }
}

fn resource() -> CatalogEntry {
    CatalogEntry {
        id: "events.list".to_owned(),
        parent_topic_id: "events".to_owned(),
        title: "List events".to_owned(),
        summary: "Read matching calendar events".to_owned(),
        intent_phrases: vec!["ultraviolet hidden phrase".to_owned()],
        related_entry_ids: vec!["events.create".to_owned()],
        guidance: Some(guidance()),
        kind: Some(catalog_entry::Kind::Resource(Resource {
            selector_type: EMPTY_TYPE.to_owned(),
            value_type: HIT_TYPE.to_owned(),
            supports_subscriptions: true,
            method: None,
        })),
    }
}

fn function(id: &str, title: &str, summary: &str) -> CatalogEntry {
    CatalogEntry {
        id: id.to_owned(),
        parent_topic_id: "events".to_owned(),
        title: title.to_owned(),
        summary: summary.to_owned(),
        guidance: Some(guidance()),
        kind: Some(catalog_entry::Kind::Function(Function {
            input_type: HIT_TYPE.to_owned(),
            output_type: HIT_TYPE.to_owned(),
            side_effect: SideEffect::WritesExternalState as i32,
            idempotency: Idempotency::Idempotent as i32,
            method: None,
        })),
        ..Default::default()
    }
}

fn workflow() -> CatalogEntry {
    CatalogEntry {
        id: "events.plan".to_owned(),
        parent_topic_id: "calendar".to_owned(),
        title: "Plan an event".to_owned(),
        summary: "Choose and create an event".to_owned(),
        guidance: Some(guidance()),
        kind: Some(catalog_entry::Kind::Workflow(Workflow {
            steps: vec![WorkflowStep {
                instruction: "List before creating".to_owned(),
                capability_id: "events.list".to_owned(),
                condition: "when duplicates matter".to_owned(),
            }],
        })),
        ..Default::default()
    }
}

fn guidance() -> Guidance {
    Guidance {
        when_to_use: "Use for calendar work".to_owned(),
        when_not_to_use: "Do not use for contacts".to_owned(),
        errors: vec![reframe_store_protocol::package::ErrorCase {
            code: "conflict".to_owned(),
            summary: "The item exists".to_owned(),
            recovery: "Read it first".to_owned(),
        }],
        examples: vec![
            Example {
                title: "First".to_owned(),
                description: "First example".to_owned(),
                input: Some(hit_any("input-one")),
                output: Some(hit_any("output-one")),
            },
            Example {
                title: "Second".to_owned(),
                description: "Second example".to_owned(),
                input: Some(hit_any("input-two")),
                output: Some(hit_any("output-two")),
            },
        ],
    }
}

pub fn hit_any(id: &str) -> Any {
    let hit = CatalogHit {
        id: id.to_owned(),
        kind: CapabilityKind::Function as i32,
        title: "Title".to_owned(),
        summary: "Summary".to_owned(),
    };
    Any {
        type_url: format!("type.googleapis.com/{HIT_TYPE}"),
        value: hit.encode_to_vec(),
    }
}

pub fn empty_any() -> Any {
    Any {
        type_url: format!("type.googleapis.com/{EMPTY_TYPE}"),
        value: GetStoreCardRequest {}.encode_to_vec(),
    }
}
