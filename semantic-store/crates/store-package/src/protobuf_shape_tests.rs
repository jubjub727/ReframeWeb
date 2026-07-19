use prost::Message;
use reframe_store_protocol::package::Manifest;
use sha2::{Digest, Sha256};

use crate::{
    PackageError, VerifiedPackage,
    protobuf_shape::{MAX_CATALOG_ENTRIES, MAX_MANIFEST_SHAPE_VALUES, MAX_SCHEMA_FILES},
    test_fixture,
};

#[test]
fn tiny_manifest_cannot_repeat_empty_messages_into_allocation_work() {
    let payload = repeated_empty_message(3, MAX_MANIFEST_SHAPE_VALUES + 1);
    assert!(payload.len() < 256);
    assert!(Manifest::decode(payload.as_slice()).is_ok());

    let archive =
        test_fixture::mutate_entry(&test_fixture::valid_archive(), "manifest.pb", |bytes| {
            *bytes = payload
        });
    assert_shape_rejection(
        VerifiedPackage::from_bytes(&archive),
        ExpectedEntry::Manifest,
    );
}

#[test]
fn descriptor_set_is_shape_checked_before_materialization() {
    let payload = repeated_empty_message(1, MAX_SCHEMA_FILES + 1);
    assert!(payload.len() < 20 * 1024);
    let archive = replace_hashed_entry("schema.binpb", payload);

    assert_shape_rejection(VerifiedPackage::from_bytes(&archive), ExpectedEntry::Schema);
}

#[test]
fn catalog_is_shape_checked_before_materialization() {
    let payload = repeated_empty_message(7, MAX_CATALOG_ENTRIES + 1);
    assert!(payload.len() < 20 * 1024);
    let archive = replace_hashed_entry("catalog.pb", payload);

    assert_shape_rejection(
        VerifiedPackage::from_bytes(&archive),
        ExpectedEntry::Catalog,
    );
}

fn repeated_empty_message(field_number: u8, count: usize) -> Vec<u8> {
    assert!(field_number < 16);
    let key = (field_number << 3) | 2;
    [key, 0].repeat(count)
}

fn replace_hashed_entry(name: &str, payload: Vec<u8>) -> Vec<u8> {
    let mut entries = test_fixture::entries(&test_fixture::valid_archive());
    entries
        .iter_mut()
        .find(|(entry_name, _)| entry_name == name)
        .expect("artifact entry")
        .1 = payload.clone();

    let manifest_bytes = &mut entries
        .iter_mut()
        .find(|(entry_name, _)| entry_name == "manifest.pb")
        .expect("manifest entry")
        .1;
    let mut manifest = Manifest::decode(manifest_bytes.as_slice()).expect("fixture manifest");
    let digest = Sha256::digest(payload).to_vec();
    match name {
        "schema.binpb" => manifest.schema_sha256 = digest,
        "catalog.pb" => manifest.catalog_sha256 = digest,
        _ => unreachable!(),
    }
    *manifest_bytes = manifest.encode_to_vec();
    test_fixture::archive(&entries)
}

fn assert_shape_rejection(result: Result<VerifiedPackage, PackageError>, entry: ExpectedEntry) {
    let error = result.expect_err("shape amplification must be rejected");
    let expected_name = match entry {
        ExpectedEntry::Manifest => "manifest.pb",
        ExpectedEntry::Schema => "schema.binpb",
        ExpectedEntry::Catalog => "catalog.pb",
    };
    let source = match error {
        PackageError::ProtobufShape {
            entry: actual_name,
            source,
        } if actual_name == expected_name => source,
        other => panic!("unexpected package error: {other:?}"),
    };
    assert!(
        source.to_string().contains("payload"),
        "unexpected shape error: {source}"
    );
}

#[derive(Clone, Copy)]
enum ExpectedEntry {
    Manifest,
    Schema,
    Catalog,
}
