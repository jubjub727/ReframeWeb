use prost::Message;
use prost_types::{Any, FileDescriptorSet, SourceCodeInfo, source_code_info};
use reframe_store_protocol::package::{Example, Manifest, catalog_entry};

use crate::{CatalogError, PackageError, VerifiedPackage, test_fixture};

#[test]
fn schema_must_decode_resolve_imports_and_preserve_source_info() {
    let malformed = test_fixture::replace_schema(&test_fixture::valid_archive(), vec![0xff]);
    assert!(matches!(
        VerifiedPackage::from_bytes(&malformed),
        Err(PackageError::SchemaDecode(_))
    ));

    let mut descriptor =
        FileDescriptorSet::decode(test_fixture::schema_bytes().as_slice()).expect("schema");
    descriptor.file[0].source_code_info = None;
    let no_source =
        test_fixture::replace_schema(&test_fixture::valid_archive(), descriptor.encode_to_vec());
    assert!(matches!(
        VerifiedPackage::from_bytes(&no_source),
        Err(PackageError::MissingSourceInfo { .. })
    ));

    descriptor.file[0].source_code_info = Some(SourceCodeInfo {
        location: vec![source_code_info::Location {
            span: vec![0, 0, 0],
            ..source_code_info::Location::default()
        }],
    });
    descriptor.file[0]
        .dependency
        .push("missing.proto".to_owned());
    let unresolved =
        test_fixture::replace_schema(&test_fixture::valid_archive(), descriptor.encode_to_vec());
    assert!(matches!(
        VerifiedPackage::from_bytes(&unresolved),
        Err(PackageError::InvalidDescriptorSet(_))
    ));
}

#[test]
fn manifest_identity_release_interface_and_protocol_are_validated() {
    let invalid_id = mutate_manifest(|manifest| manifest.store_id = "Bad Store".to_owned());
    assert!(matches!(
        VerifiedPackage::from_bytes(&invalid_id),
        Err(PackageError::InvalidStoreId(_))
    ));

    let invalid_release = mutate_manifest(|manifest| manifest.store_version = "latest".to_owned());
    assert!(matches!(
        VerifiedPackage::from_bytes(&invalid_release),
        Err(PackageError::InvalidStoreVersion { .. })
    ));

    let unsupported = mutate_manifest(|manifest| {
        manifest
            .minimum_protocol_version
            .as_mut()
            .expect("version")
            .minor = 99;
    });
    assert!(matches!(
        VerifiedPackage::from_bytes(&unsupported),
        Err(PackageError::UnsupportedProtocol {
            major: 1,
            minor: 99
        })
    ));
}

#[test]
fn catalog_identity_relationships_and_method_types_cannot_drift() {
    let base = test_fixture::valid_archive();
    let mut catalog = verified_catalog(&base);
    catalog.store_id = "dev.reframe.somewhere-else".to_owned();
    let mismatch = test_fixture::replace_catalog(&base, &catalog);
    assert_catalog_error(mismatch, |error| {
        matches!(error, CatalogError::StoreIdMismatch)
    });

    let mut catalog = verified_catalog(&base);
    catalog
        .entries
        .iter_mut()
        .find(|entry| entry.id == "fixture.read")
        .expect("resource")
        .parent_topic_id = "missing".to_owned();
    let missing = test_fixture::replace_catalog(&base, &catalog);
    assert_catalog_error(missing, |error| {
        matches!(error, CatalogError::MissingRelation { .. })
    });

    let mut catalog = verified_catalog(&base);
    let entry = catalog
        .entries
        .iter_mut()
        .find(|entry| entry.id == "fixture.read")
        .expect("resource");
    let Some(catalog_entry::Kind::Resource(resource)) = entry.kind.as_mut() else {
        panic!("resource kind")
    };
    resource.value_type = "fixture.Output".to_owned();
    let drift = test_fixture::replace_catalog(&base, &catalog);
    assert_catalog_error(drift, |error| {
        matches!(error, CatalogError::MethodTypeMismatch { .. })
    });
}

#[test]
fn discovery_metadata_is_bounded_and_guidance_must_be_meaningful() {
    let base = test_fixture::valid_archive();
    let mut catalog = verified_catalog(&base);
    let resource = catalog
        .entries
        .iter_mut()
        .find(|entry| entry.id == "fixture.read")
        .expect("resource");
    resource.intent_phrases = (0..33).map(|index| format!("intent {index}")).collect();
    let oversized = test_fixture::replace_catalog(&base, &catalog);
    assert_catalog_error(oversized, |error| {
        matches!(error, CatalogError::MetadataLimit { .. })
    });

    let mut catalog = verified_catalog(&base);
    let guidance = catalog
        .entries
        .iter_mut()
        .find(|entry| entry.id == "fixture.read")
        .expect("resource")
        .guidance
        .as_mut()
        .expect("guidance");
    guidance.when_to_use.clear();
    guidance.when_not_to_use.clear();
    let empty = test_fixture::replace_catalog(&base, &catalog);
    assert_catalog_error(empty, |error| {
        matches!(error, CatalogError::MissingGuidance { .. })
    });
}

#[test]
fn examples_are_reflectively_type_checked_and_decoded() {
    let base = test_fixture::valid_archive();
    let mut catalog = verified_catalog(&base);
    add_resource_example(
        &mut catalog,
        Any {
            type_url: "type.googleapis.com/fixture.Output".to_owned(),
            value: Vec::new(),
        },
    );
    let wrong_type = test_fixture::replace_catalog(&base, &catalog);
    assert_catalog_error(wrong_type, |error| {
        matches!(
            error,
            CatalogError::ExampleTypeMismatch {
                direction: "input",
                ..
            }
        )
    });

    let mut catalog = verified_catalog(&base);
    add_resource_example(
        &mut catalog,
        Any {
            type_url: "type.googleapis.com/fixture.Selector".to_owned(),
            value: vec![0x80],
        },
    );
    let malformed = test_fixture::replace_catalog(&base, &catalog);
    assert_catalog_error(malformed, |error| {
        matches!(
            error,
            CatalogError::InvalidExamplePayload {
                direction: "input",
                ..
            }
        )
    });
}

#[test]
fn protobuf_streaming_bindings_are_rejected_even_without_annotations() {
    let base = test_fixture::valid_archive();
    let mut descriptor =
        FileDescriptorSet::decode(test_fixture::schema_bytes().as_slice()).expect("schema");
    descriptor.file[0].service[0].method[0].server_streaming = Some(true);
    let streaming = test_fixture::replace_schema(&base, descriptor.encode_to_vec());

    assert_catalog_error(streaming, |error| {
        matches!(
            error,
            CatalogError::StreamingMethodBinding { entry_id, .. }
                if entry_id == "fixture.read"
        )
    });
}

#[test]
fn legacy_schema_without_the_capability_extension_remains_supported() {
    VerifiedPackage::from_bytes(&test_fixture::valid_archive()).expect("legacy package");
}

#[test]
fn catalog_revision_changes_when_only_exact_schema_bytes_change() {
    let base = test_fixture::valid_archive();
    let previous = VerifiedPackage::from_bytes(&base).expect("previous");
    let mut padded_schema = test_fixture::schema_bytes();
    // Unknown root field 100 with varint value 1: semantically inert, byte-distinct.
    padded_schema.extend_from_slice(&[0xa0, 0x06, 0x01]);
    let changed = test_fixture::replace_schema(&base, padded_schema);
    let candidate = VerifiedPackage::from_bytes(&changed).expect("candidate");

    assert_eq!(previous.catalog_bytes(), candidate.catalog_bytes());
    assert_ne!(previous.schema_hash(), candidate.schema_hash());
    assert_ne!(previous.catalog_revision(), candidate.catalog_revision());
}

fn mutate_manifest(mutate: impl FnOnce(&mut Manifest)) -> Vec<u8> {
    test_fixture::mutate_entry(&test_fixture::valid_archive(), "manifest.pb", |bytes| {
        let mut manifest = Manifest::decode(bytes.as_slice()).expect("manifest");
        mutate(&mut manifest);
        *bytes = manifest.encode_to_vec();
    })
}

fn verified_catalog(base: &[u8]) -> reframe_store_protocol::package::Catalog {
    VerifiedPackage::from_bytes(base)
        .expect("base package")
        .catalog()
        .clone()
}

fn add_resource_example(catalog: &mut reframe_store_protocol::package::Catalog, input: Any) {
    let guidance = catalog
        .entries
        .iter_mut()
        .find(|entry| entry.id == "fixture.read")
        .expect("resource")
        .guidance
        .as_mut()
        .expect("guidance");
    guidance.examples.push(Example {
        title: "Typed example".to_owned(),
        description: "A reflectively checked example.".to_owned(),
        input: Some(input),
        output: Some(Any {
            type_url: "type.googleapis.com/fixture.Value".to_owned(),
            value: Vec::new(),
        }),
    });
}

fn assert_catalog_error(archive: Vec<u8>, predicate: impl FnOnce(&CatalogError) -> bool) {
    let error = VerifiedPackage::from_bytes(&archive).expect_err("invalid catalog");
    let PackageError::InvalidCatalog(error) = error else {
        panic!("unexpected error: {error}")
    };
    assert!(predicate(&error), "unexpected catalog error: {error}");
}
