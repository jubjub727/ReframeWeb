use prost::Message;
use reframe_store_protocol::{
    CURRENT_PROTOCOL_VERSION,
    package::{
        CatalogEntry, Example, Idempotency, InterfaceVersion, MethodBinding, Resource, SideEffect,
        catalog_entry,
    },
};

use crate::{
    CatalogError, PackageBuilder, PackageError, PackageIdentity, generate_catalog,
    schema_uses_annotations, test_fixture,
};

use super::support::{
    assert_fixture_error, authored, authored_with_workflow, empty_any, entry, function, resource,
    valid_schema,
};

#[test]
fn generation_merges_authored_content_and_derives_bindings_in_id_order() {
    let catalog = generate_catalog(valid_schema(), authored_with_workflow()).expect("catalog");

    assert_eq!(catalog.top_level_topic_ids, ["fixture"]);
    assert_eq!(
        catalog
            .entries
            .iter()
            .map(|entry| entry.id.as_str())
            .collect::<Vec<_>>(),
        [
            "fixture",
            "fixture.call",
            "fixture.read",
            "fixture.workflow"
        ]
    );
    let resource = resource(&catalog.entries, "fixture.read");
    assert_eq!(resource.selector_type, "annotated_fixture.Selector");
    assert_eq!(resource.value_type, "annotated_fixture.Value");
    assert_eq!(
        resource.method,
        Some(MethodBinding {
            service: "annotated_fixture.Store".to_owned(),
            method: "Read".to_owned(),
        })
    );
    let function = function(&catalog.entries, "fixture.call");
    assert_eq!(function.input_type, "annotated_fixture.Input");
    assert_eq!(function.output_type, "annotated_fixture.Output");
    assert_eq!(function.side_effect, SideEffect::None as i32);
    assert_eq!(function.idempotency, Idempotency::Idempotent as i32);
    assert_eq!(
        entry(&catalog.entries, "fixture.call")
            .guidance
            .as_ref()
            .expect("guidance")
            .examples
            .len(),
        1
    );
}

#[test]
fn generation_is_byte_deterministic() {
    let authored = authored_with_workflow();
    let first = generate_catalog(valid_schema(), authored.clone())
        .expect("first")
        .encode_to_vec();
    let second = generate_catalog(valid_schema(), authored)
        .expect("second")
        .encode_to_vec();
    assert_eq!(first, second);
}

#[test]
fn annotation_detection_distinguishes_production_and_legacy_schemas() {
    assert!(
        schema_uses_annotations(valid_schema(), test_fixture::STORE_ID).expect("annotated schema")
    );
    assert!(
        !schema_uses_annotations(&test_fixture::schema_bytes(), test_fixture::STORE_ID)
            .expect("legacy schema")
    );
}

#[test]
fn invalid_annotations_and_authored_content_are_rejected() {
    assert!(matches!(
        generate_catalog(&test_fixture::schema_bytes(), authored()),
        Err(CatalogError::MissingCapabilityExtension)
    ));
    assert_fixture_errors();

    let mut invalid = authored();
    invalid.entries.push(CatalogEntry {
        id: "authored.resource".to_owned(),
        kind: Some(catalog_entry::Kind::Resource(Resource::default())),
        ..CatalogEntry::default()
    });
    assert!(matches!(
        generate_catalog(valid_schema(), invalid),
        Err(CatalogError::InvalidAuthoredEntryKind { entry_id })
            if entry_id == "authored.resource"
    ));

    let mut unknown_examples = authored();
    unknown_examples
        .examples_by_capability
        .insert("fixture.missing".to_owned(), Vec::new());
    assert!(matches!(
        generate_catalog(valid_schema(), unknown_examples),
        Err(CatalogError::UnknownExampleTarget { entry_id })
            if entry_id == "fixture.missing"
    ));

    let mut wrong_type = authored();
    wrong_type.examples_by_capability.insert(
        "fixture.call".to_owned(),
        vec![Example {
            title: "Wrong input type".to_owned(),
            description: String::new(),
            input: Some(empty_any("annotated_fixture.Output")),
            output: Some(empty_any("annotated_fixture.Output")),
        }],
    );
    assert!(matches!(
        generate_catalog(valid_schema(), wrong_type),
        Err(CatalogError::ExampleTypeMismatch {
            entry_id,
            direction: "input",
            ..
        }) if entry_id == "fixture.call"
    ));
}

#[test]
fn annotated_builder_rejects_a_store_identity_mismatch() {
    let error = PackageBuilder::from_annotated_schema(
        PackageIdentity::new(
            "dev.reframe.different",
            "1.2.3",
            InterfaceVersion { major: 1, minor: 2 },
            CURRENT_PROTOCOL_VERSION,
        ),
        b"\0asm\x01\0\0\0".to_vec(),
        valid_schema(),
        authored(),
    )
    .expect_err("Store ID mismatch");

    assert!(matches!(
        error,
        PackageError::InvalidCatalog(CatalogError::StoreIdMismatch)
    ));
}

fn assert_fixture_errors() {
    assert_fixture_error(
        "annotated_duplicate",
        |error| matches!(error, CatalogError::DuplicateEntry { entry_id } if entry_id == "duplicate.capability"),
    );
    assert_fixture_error("annotated_missing_kind", |error| {
        matches!(error, CatalogError::MissingCapabilityKind { .. })
    });
    assert_fixture_error(
        "annotated_invalid_store_service",
        |error| matches!(error, CatalogError::InvalidStoreServiceAnnotation { service, .. } if service == "annotated_invalid_store_service.Store"),
    );
    assert_fixture_error(
        "annotated_empty_store",
        |error| matches!(error, CatalogError::MissingAnnotatedCapabilities { store_id } if store_id == test_fixture::STORE_ID),
    );
    assert_fixture_error(
        "annotated_unannotated_method",
        |error| matches!(error, CatalogError::MissingMethodCapabilityAnnotation { method } if method == "annotated_unannotated_method.Store.Hidden"),
    );
    assert_fixture_error(
        "annotated_unspecified_function",
        |error| matches!(error, CatalogError::IncompleteFunctionMetadata { entry_id } if entry_id == "incomplete.function"),
    );
    assert_fixture_error(
        "annotated_streaming",
        |error| matches!(error, CatalogError::StreamingMethodBinding { entry_id, .. } if entry_id == "streaming.invalid"),
    );
}
