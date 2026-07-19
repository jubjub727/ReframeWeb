mod support;

use std::sync::Arc;

use prost::Message;
use prost_reflect::DescriptorPool;
use prost_types::{
    DescriptorProto, EnumDescriptorProto, EnumValueDescriptorProto, FieldDescriptorProto,
    FileDescriptorProto, FileDescriptorSet, MessageOptions, OneofDescriptorProto,
    field_descriptor_proto::{Label, Type},
};
use reframe_store_catalog::{CatalogError, CatalogService, MAX_SCHEMA_DEPTH};
use reframe_store_protocol::wire::{
    GetSchemaBundleRequest, InspectCapabilityRequest, InspectTypeRequest, InspectionSection,
    get_schema_bundle_response,
};

use support::{empty_catalog, service};

#[test]
fn capability_inspection_returns_only_requested_sections_and_limits_examples() {
    let service = service();
    let response = service
        .inspect_capability(&InspectCapabilityRequest {
            capability_id: "events.create".to_owned(),
            sections: vec![
                InspectionSection::Summary as i32,
                InspectionSection::Input as i32,
                InspectionSection::Examples as i32,
                InspectionSection::SideEffects as i32,
            ],
            schema_depth: 99,
            example_limit: 1,
            ..Default::default()
        })
        .expect("selective inspection");
    assert!(response.summary.is_some());
    assert!(response.input.is_some());
    assert!(response.output.is_none());
    assert!(response.when_to_use.is_none());
    assert!(response.errors.is_empty());
    assert_eq!(response.examples.len(), 1);
    assert!(response.side_effects.is_some());
}

#[test]
fn capability_inspection_enforces_the_encoded_response_budget() {
    let service = service();
    let full = service
        .inspect_capability(&InspectCapabilityRequest {
            capability_id: "events.create".to_owned(),
            sections: vec![
                InspectionSection::Input as i32,
                InspectionSection::Output as i32,
                InspectionSection::Examples as i32,
            ],
            example_limit: 2,
            ..Default::default()
        })
        .expect("full inspection");
    let constrained = service
        .inspect_capability(&InspectCapabilityRequest {
            capability_id: "events.create".to_owned(),
            sections: vec![
                InspectionSection::Input as i32,
                InspectionSection::Output as i32,
                InspectionSection::Examples as i32,
            ],
            example_limit: 2,
            byte_budget: u32::try_from(full.encoded_len() - 1).expect("small response"),
            ..Default::default()
        })
        .expect("bounded inspection");
    assert!(constrained.encoded_len() < full.encoded_len());

    let baseline = service
        .inspect_capability(&InspectCapabilityRequest {
            capability_id: "events.create".to_owned(),
            ..Default::default()
        })
        .expect("baseline");
    assert_eq!(
        service.inspect_capability(&InspectCapabilityRequest {
            capability_id: "events.create".to_owned(),
            byte_budget: u32::try_from(baseline.encoded_len() - 1).expect("small baseline"),
            ..Default::default()
        }),
        Err(CatalogError::BudgetExceeded {
            budget: baseline.encoded_len() - 1,
            required: baseline.encoded_len(),
        })
    );
}

#[test]
fn type_projection_handles_maps_oneofs_presence_recursion_and_field_paths() {
    let service = type_service();
    let response = service
        .inspect_type(&InspectTypeRequest {
            type_name: ".test.Node".to_owned(),
            field_paths: vec![
                "labels".to_owned(),
                "text".to_owned(),
                "next.name".to_owned(),
            ],
            depth: u32::try_from(MAX_SCHEMA_DEPTH + 8).expect("small depth"),
            ..Default::default()
        })
        .expect("type projection");
    let view = response.r#type.expect("type view");
    assert_eq!(
        view.fields
            .iter()
            .map(|field| field.name.as_str())
            .collect::<Vec<_>>(),
        ["next", "labels", "text"]
    );
    assert!(view.recursive);
    let next = view
        .fields
        .iter()
        .find(|field| field.name == "next")
        .expect("next");
    assert!(next.recursive);
    assert!(next.supports_presence);
    assert_eq!(
        next.nested
            .as_ref()
            .expect("explicit recursive projection")
            .fields[0]
            .name,
        "name"
    );
    let labels = view
        .fields
        .iter()
        .find(|field| field.name == "labels")
        .expect("map");
    assert!(labels.is_map);
    assert_eq!(labels.type_name, "map<string, string>");
    assert_eq!(labels.nested.as_ref().expect("map entry").fields.len(), 2);
    let text = view
        .fields
        .iter()
        .find(|field| field.name == "text")
        .expect("oneof");
    assert_eq!(text.oneof_name, "choice");
    assert!(text.supports_presence);
    let nickname = service
        .inspect_type(&InspectTypeRequest {
            type_name: "test.Node".to_owned(),
            field_paths: vec!["nickname".to_owned()],
            ..Default::default()
        })
        .expect("optional projection")
        .r#type
        .expect("view")
        .fields
        .pop()
        .expect("nickname");
    assert!(nickname.supports_presence);
    assert!(nickname.oneof_name.is_empty());
}

#[test]
fn type_depth_and_budget_mark_complete_projections_as_truncated() {
    let service = type_service();
    let depth_one = service
        .inspect_type(&InspectTypeRequest {
            type_name: "test.Node".to_owned(),
            depth: 1,
            ..Default::default()
        })
        .expect("depth one")
        .r#type
        .expect("view");
    let labels = depth_one
        .fields
        .iter()
        .find(|field| field.name == "labels")
        .expect("labels");
    assert!(labels.nested.is_none());
    assert!(labels.truncated);

    let full = service
        .inspect_type(&InspectTypeRequest {
            type_name: "test.Node".to_owned(),
            depth: 4,
            ..Default::default()
        })
        .expect("full view");
    let budget = full.encoded_len() - 1;
    let bounded = service
        .inspect_type(&InspectTypeRequest {
            type_name: "test.Node".to_owned(),
            depth: 4,
            byte_budget: u32::try_from(budget).expect("small view"),
            ..Default::default()
        })
        .expect("bounded view");
    assert!(bounded.encoded_len() <= budget);
    assert!(bounded.r#type.expect("view").truncated);
}

#[test]
fn schema_bundle_preserves_exact_bytes_and_supports_unchanged() {
    let service = service();
    let raw = reframe_store_protocol::descriptor_set_bytes();
    let response = service
        .get_schema_bundle(&GetSchemaBundleRequest::default())
        .expect("schema bundle");
    assert_eq!(response.artifact_hash, service.schema_artifact_hash());
    assert_eq!(
        response.result,
        Some(get_schema_bundle_response::Result::DescriptorSet(
            raw.to_vec()
        ))
    );
    let unchanged = service
        .get_schema_bundle(&GetSchemaBundleRequest {
            known_artifact_hash: service.schema_artifact_hash().to_vec(),
        })
        .expect("unchanged marker");
    assert_eq!(
        unchanged.result,
        Some(get_schema_bundle_response::Result::Unchanged(true))
    );
}

fn type_service() -> CatalogService {
    let descriptor_set = FileDescriptorSet {
        file: vec![FileDescriptorProto {
            name: Some("types.proto".to_owned()),
            package: Some("test".to_owned()),
            syntax: Some("proto3".to_owned()),
            message_type: vec![node_descriptor()],
            enum_type: vec![EnumDescriptorProto {
                name: Some("Status".to_owned()),
                value: vec![
                    EnumValueDescriptorProto {
                        name: Some("STATUS_UNSPECIFIED".to_owned()),
                        number: Some(0),
                        ..Default::default()
                    },
                    EnumValueDescriptorProto {
                        name: Some("STATUS_READY".to_owned()),
                        number: Some(1),
                        ..Default::default()
                    },
                ],
                ..Default::default()
            }],
            ..Default::default()
        }],
    };
    let pool = DescriptorPool::from_file_descriptor_set(descriptor_set.clone()).expect("pool");
    let bytes = descriptor_set.encode_to_vec();
    CatalogService::new(empty_catalog(), pool, Arc::from(bytes), [4; 32]).expect("service")
}

fn node_descriptor() -> DescriptorProto {
    let map_entry = DescriptorProto {
        name: Some("LabelsEntry".to_owned()),
        field: vec![
            field("key", 1, Label::Optional, Type::String, None, None),
            field("value", 2, Label::Optional, Type::String, None, None),
        ],
        options: Some(MessageOptions {
            map_entry: Some(true),
            ..Default::default()
        }),
        ..Default::default()
    };
    let mut nickname = field("nickname", 7, Label::Optional, Type::String, None, Some(1));
    nickname.proto3_optional = Some(true);
    DescriptorProto {
        name: Some("Node".to_owned()),
        field: vec![
            field("name", 1, Label::Optional, Type::String, None, None),
            field(
                "next",
                2,
                Label::Optional,
                Type::Message,
                Some(".test.Node"),
                None,
            ),
            field(
                "labels",
                3,
                Label::Repeated,
                Type::Message,
                Some(".test.Node.LabelsEntry"),
                None,
            ),
            field("text", 4, Label::Optional, Type::String, None, Some(0)),
            field("number", 5, Label::Optional, Type::Int32, None, Some(0)),
            field(
                "status",
                6,
                Label::Optional,
                Type::Enum,
                Some(".test.Status"),
                None,
            ),
            nickname,
        ],
        nested_type: vec![map_entry],
        oneof_decl: vec![
            OneofDescriptorProto {
                name: Some("choice".to_owned()),
                ..Default::default()
            },
            OneofDescriptorProto {
                name: Some("_nickname".to_owned()),
                ..Default::default()
            },
        ],
        ..Default::default()
    }
}

fn field(
    name: &str,
    number: i32,
    label: Label,
    field_type: Type,
    type_name: Option<&str>,
    oneof_index: Option<i32>,
) -> FieldDescriptorProto {
    FieldDescriptorProto {
        name: Some(name.to_owned()),
        number: Some(number),
        label: Some(label as i32),
        r#type: Some(field_type as i32),
        type_name: type_name.map(ToOwned::to_owned),
        oneof_index,
        ..Default::default()
    }
}
