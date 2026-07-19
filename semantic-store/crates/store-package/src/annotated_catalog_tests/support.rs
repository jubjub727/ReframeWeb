use std::collections::BTreeMap;

use prost_types::Any;
use reframe_store_protocol::{
    CURRENT_PROTOCOL_VERSION,
    package::{
        CatalogEntry, Example, Function, Guidance, InterfaceVersion, MethodBinding, Resource,
        Topic, Workflow, WorkflowStep, catalog_entry,
    },
};

use crate::{
    AuthoredCatalog, CatalogError, PackageBuilder, PackageError, PackageIdentity, VerifiedPackage,
    generate_catalog, test_fixture,
};

use super::fixture_schemas;

pub(super) fn valid_schema() -> &'static [u8] {
    fixture_schemas::schema("annotated_valid")
}

pub(super) fn annotated_archive() -> Vec<u8> {
    PackageBuilder::from_annotated_schema(
        PackageIdentity::new(
            test_fixture::STORE_ID,
            "1.2.3",
            InterfaceVersion { major: 1, minor: 2 },
            CURRENT_PROTOCOL_VERSION,
        ),
        b"\0asm\x01\0\0\0".to_vec(),
        valid_schema(),
        authored(),
    )
    .expect("annotated builder")
    .build()
    .expect("annotated package")
}

pub(super) fn authored() -> AuthoredCatalog {
    AuthoredCatalog {
        store_id: test_fixture::STORE_ID.to_owned(),
        display_name: "Annotated Fixture Store".to_owned(),
        overview_sentences: [
            "Provides deterministic annotated fixture data.".to_owned(),
            "Exercises production catalog generation and drift checks.".to_owned(),
        ],
        entries: vec![topic()],
        examples_by_capability: BTreeMap::new(),
    }
}

pub(super) fn authored_with_workflow() -> AuthoredCatalog {
    let mut authored = authored();
    authored.entries.push(CatalogEntry {
        id: "fixture.workflow".to_owned(),
        parent_topic_id: "fixture".to_owned(),
        title: "Fixture workflow".to_owned(),
        summary: "Reads fixture data before invoking its deterministic function.".to_owned(),
        guidance: Some(Guidance {
            when_to_use: "Use to exercise authored workflows.".to_owned(),
            when_not_to_use: "Do not use outside tests.".to_owned(),
            ..Guidance::default()
        }),
        kind: Some(catalog_entry::Kind::Workflow(Workflow {
            steps: vec![WorkflowStep {
                instruction: "Read the deterministic fixture value.".to_owned(),
                capability_id: "fixture.read".to_owned(),
                condition: String::new(),
            }],
        })),
        ..CatalogEntry::default()
    });
    authored.examples_by_capability.insert(
        "fixture.call".to_owned(),
        vec![Example {
            title: "Deterministic call".to_owned(),
            description: "Invokes the typed empty fixture messages.".to_owned(),
            input: Some(empty_any("annotated_fixture.Input")),
            output: Some(empty_any("annotated_fixture.Output")),
        }],
    );
    authored
}

pub(super) fn unannotated_resource() -> CatalogEntry {
    CatalogEntry {
        id: "fixture.legacy".to_owned(),
        parent_topic_id: "fixture".to_owned(),
        title: "Legacy fixture".to_owned(),
        summary: "Binds an unannotated descriptor method.".to_owned(),
        guidance: Some(Guidance {
            when_to_use: "Use only to test drift rejection.".to_owned(),
            when_not_to_use: "Do not package this capability.".to_owned(),
            ..Guidance::default()
        }),
        kind: Some(catalog_entry::Kind::Resource(Resource {
            selector_type: "annotated_fixture.Selector".to_owned(),
            value_type: "annotated_fixture.Value".to_owned(),
            supports_subscriptions: false,
            method: Some(MethodBinding {
                service: "annotated_fixture.Helper".to_owned(),
                method: "Legacy".to_owned(),
            }),
        })),
        ..CatalogEntry::default()
    }
}

pub(super) fn empty_any(type_name: &str) -> Any {
    Any {
        type_url: format!("type.googleapis.com/{type_name}"),
        value: Vec::new(),
    }
}

pub(super) fn entry<'a>(entries: &'a [CatalogEntry], id: &str) -> &'a CatalogEntry {
    entries.iter().find(|entry| entry.id == id).expect("entry")
}

pub(super) fn entry_mut<'a>(entries: &'a mut [CatalogEntry], id: &str) -> &'a mut CatalogEntry {
    entries
        .iter_mut()
        .find(|entry| entry.id == id)
        .expect("entry")
}

pub(super) fn resource<'a>(entries: &'a [CatalogEntry], id: &str) -> &'a Resource {
    let Some(catalog_entry::Kind::Resource(resource)) = entry(entries, id).kind.as_ref() else {
        panic!("resource")
    };
    resource
}

pub(super) fn function<'a>(entries: &'a [CatalogEntry], id: &str) -> &'a Function {
    let Some(catalog_entry::Kind::Function(function)) = entry(entries, id).kind.as_ref() else {
        panic!("function")
    };
    function
}

pub(super) fn assert_fixture_error(fixture: &str, predicate: impl FnOnce(&CatalogError) -> bool) {
    let bytes = fixture_schemas::schema(fixture);
    let error = generate_catalog(bytes, authored()).expect_err("invalid annotations");
    assert!(predicate(&error), "unexpected catalog error: {error}");
}

pub(super) fn assert_catalog_error(
    archive: Vec<u8>,
    predicate: impl FnOnce(&CatalogError) -> bool,
) {
    let error = VerifiedPackage::from_bytes(&archive).expect_err("invalid package");
    let PackageError::InvalidCatalog(error) = error else {
        panic!("unexpected package error: {error}")
    };
    assert!(predicate(&error), "unexpected catalog error: {error}");
}

fn topic() -> CatalogEntry {
    CatalogEntry {
        id: "fixture".to_owned(),
        title: "Fixture".to_owned(),
        summary: "Capabilities used to verify annotated Store packages.".to_owned(),
        kind: Some(catalog_entry::Kind::Topic(Topic {})),
        ..CatalogEntry::default()
    }
}
