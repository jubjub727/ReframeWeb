use prost_reflect::{DescriptorPool, MessageDescriptor};

use crate::{
    PayloadShapeError, ProtobufShapeBudget, RepeatedFieldLimit, UnknownFieldPolicy,
    descriptor_set_bytes, validate_message_shape,
};

const CATALOG_ENTRY_LIMIT: &[RepeatedFieldLimit] = &[RepeatedFieldLimit {
    message_full_name: "reframe.semantic_store.package.v1.Catalog",
    field_number: 7,
    maximum_values: 2,
}];

const SOURCE_PATH_LIMIT: &[RepeatedFieldLimit] = &[RepeatedFieldLimit {
    message_full_name: "google.protobuf.SourceCodeInfo.Location",
    field_number: 1,
    maximum_values: 2,
}];

#[test]
fn unknown_field_policy_is_explicit_and_skipping_still_checks_wire_data() {
    let descriptor = message("reframe.semantic_store.package.v1.Manifest");
    let unknown_varint = [0xa0, 0x06, 0x01];
    let limits = ProtobufShapeBudget::new(16, 4);

    assert!(matches!(
        validate_message_shape(
            &descriptor,
            &unknown_varint,
            limits,
            UnknownFieldPolicy::Reject,
        ),
        Err(PayloadShapeError::UnknownField)
    ));
    validate_message_shape(
        &descriptor,
        &unknown_varint,
        limits,
        UnknownFieldPolicy::Skip,
    )
    .expect("well-formed unknown field");

    let truncated_unknown_bytes = [0xa2, 0x06, 0x02, 0x01];
    assert!(matches!(
        validate_message_shape(
            &descriptor,
            &truncated_unknown_bytes,
            limits,
            UnknownFieldPolicy::Skip,
        ),
        Err(PayloadShapeError::TruncatedField)
    ));

    let nested_unknown_groups = [0xa3, 0x06, 0xa3, 0x06, 0xa4, 0x06, 0xa4, 0x06];
    assert!(matches!(
        validate_message_shape(
            &descriptor,
            &nested_unknown_groups,
            ProtobufShapeBudget::new(16, 1),
            UnknownFieldPolicy::Skip,
        ),
        Err(PayloadShapeError::NestingLimit)
    ));
}

#[test]
fn repeated_message_cardinality_is_checked_without_decoding_nodes() {
    let descriptor = message("reframe.semantic_store.package.v1.Catalog");
    let three_empty_entries = [0x3a, 0, 0x3a, 0, 0x3a, 0];
    let limits = ProtobufShapeBudget::new(32, 4)
        .with_maximum_messages(8)
        .with_repeated_field_limits(CATALOG_ENTRY_LIMIT);

    assert!(matches!(
        validate_message_shape(
            &descriptor,
            &three_empty_entries,
            limits,
            UnknownFieldPolicy::Reject,
        ),
        Err(PayloadShapeError::RepeatedFieldLimit)
    ));
}

#[test]
fn packed_repeated_cardinality_counts_decoded_elements() {
    let descriptor = message("google.protobuf.SourceCodeInfo.Location");
    let three_packed_path_items = [0x0a, 0x03, 1, 2, 3];
    let limits = ProtobufShapeBudget::new(32, 4).with_repeated_field_limits(SOURCE_PATH_LIMIT);

    assert!(matches!(
        validate_message_shape(
            &descriptor,
            &three_packed_path_items,
            limits,
            UnknownFieldPolicy::Reject,
        ),
        Err(PayloadShapeError::RepeatedFieldLimit)
    ));
}

fn message(name: &str) -> MessageDescriptor {
    DescriptorPool::decode(descriptor_set_bytes())
        .expect("fixed descriptor set")
        .get_message_by_name(name)
        .expect("fixed message")
}
