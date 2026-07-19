use std::sync::OnceLock;

use prost_reflect::{DescriptorPool, MessageDescriptor};
use reframe_store_protocol::{
    PayloadShapeError, ProtobufShapeBudget, RepeatedFieldLimit, UnknownFieldPolicy,
    descriptor_set_bytes, validate_message_shape,
};

const MANIFEST_NAME: &str = "reframe.semantic_store.package.v1.Manifest";
const CATALOG_NAME: &str = "reframe.semantic_store.package.v1.Catalog";
const DESCRIPTOR_SET_NAME: &str = "google.protobuf.FileDescriptorSet";

// A canonical manifest has eleven values. This leaves room for protobuf field
// repetition without permitting a tiny manifest to drive unbounded merge work.
pub(crate) const MAX_MANIFEST_SHAPE_VALUES: usize = 64;

// The catalog contract permits 4,096 entries. Its per-entry list limits admit
// fewer than 384 structural values even when all guidance and workflow limits
// are populated, with a further 256 values reserved for the Store card.
pub(crate) const MAX_CATALOG_SHAPE_VALUES: usize = 4_096 * 384 + 256;

// Descriptor source information and annotations are structurally denser than
// catalog entries. This allows 256 values per maximum catalog capability plus
// ample fixed/import overhead while rejecting million-node amplification.
pub(crate) const MAX_SCHEMA_SHAPE_VALUES: usize = 4_096 * 256 + 65_536;

const MAX_MANIFEST_MESSAGES: usize = 16;
const MAX_CATALOG_MESSAGES: usize = 320_000;
const MAX_SCHEMA_MESSAGES: usize = 262_144;
// Preflight cardinalities intentionally leave validation headroom so ordinary
// one-over contract errors retain their established CatalogError variants.
pub(crate) const MAX_CATALOG_ENTRIES: usize = 8_192;
pub(crate) const MAX_SCHEMA_FILES: usize = 8_192;

const CATALOG_FIELD_LIMITS: &[RepeatedFieldLimit] = &[
    field_limit(CATALOG_NAME, 5, 16),
    field_limit(CATALOG_NAME, 6, 64),
    field_limit(CATALOG_NAME, 7, MAX_CATALOG_ENTRIES),
    field_limit("reframe.semantic_store.package.v1.CatalogEntry", 5, 64),
    field_limit("reframe.semantic_store.package.v1.CatalogEntry", 6, 64),
    field_limit("reframe.semantic_store.package.v1.Guidance", 3, 32),
    field_limit("reframe.semantic_store.package.v1.Guidance", 4, 16),
    field_limit("reframe.semantic_store.package.v1.Workflow", 1, 64),
];

const SCHEMA_FIELD_LIMITS: &[RepeatedFieldLimit] = &[
    field_limit(DESCRIPTOR_SET_NAME, 1, MAX_SCHEMA_FILES),
    field_limit("google.protobuf.FileDescriptorProto", 3, 4_096),
    field_limit("google.protobuf.FileDescriptorProto", 4, 16_384),
    field_limit("google.protobuf.FileDescriptorProto", 5, 16_384),
    field_limit("google.protobuf.FileDescriptorProto", 6, 16_384),
    field_limit("google.protobuf.FileDescriptorProto", 7, 16_384),
    field_limit("google.protobuf.DescriptorProto", 2, 16_384),
    field_limit("google.protobuf.DescriptorProto", 3, 16_384),
    field_limit("google.protobuf.DescriptorProto", 4, 16_384),
    field_limit("google.protobuf.DescriptorProto", 5, 16_384),
    field_limit("google.protobuf.DescriptorProto", 6, 16_384),
    field_limit("google.protobuf.DescriptorProto", 8, 16_384),
    field_limit("google.protobuf.DescriptorProto", 9, 16_384),
    field_limit("google.protobuf.DescriptorProto", 10, 16_384),
    field_limit("google.protobuf.EnumDescriptorProto", 2, 16_384),
    field_limit("google.protobuf.EnumDescriptorProto", 4, 16_384),
    field_limit("google.protobuf.EnumDescriptorProto", 5, 16_384),
    field_limit("google.protobuf.ServiceDescriptorProto", 2, 16_384),
    field_limit("google.protobuf.SourceCodeInfo", 1, 65_536),
    field_limit("google.protobuf.UninterpretedOption", 2, 256),
];

const fn field_limit(
    message_full_name: &'static str,
    field_number: u32,
    maximum_values: usize,
) -> RepeatedFieldLimit {
    RepeatedFieldLimit {
        message_full_name,
        field_number,
        maximum_values,
    }
}

pub(crate) fn validate_manifest(bytes: &[u8]) -> Result<(), PayloadShapeError> {
    validate(
        &fixed_descriptors().manifest,
        bytes,
        ProtobufShapeBudget::new(MAX_MANIFEST_SHAPE_VALUES, 4)
            .with_maximum_messages(MAX_MANIFEST_MESSAGES),
    )
}

pub(crate) fn validate_schema(bytes: &[u8]) -> Result<(), PayloadShapeError> {
    validate(
        &fixed_descriptors().descriptor_set,
        bytes,
        ProtobufShapeBudget::new(MAX_SCHEMA_SHAPE_VALUES, 64)
            .with_maximum_messages(MAX_SCHEMA_MESSAGES)
            .with_repeated_field_limits(SCHEMA_FIELD_LIMITS),
    )
}

pub(crate) fn validate_catalog(bytes: &[u8]) -> Result<(), PayloadShapeError> {
    validate(
        &fixed_descriptors().catalog,
        bytes,
        ProtobufShapeBudget::new(MAX_CATALOG_SHAPE_VALUES, 8)
            .with_maximum_messages(MAX_CATALOG_MESSAGES)
            .with_repeated_field_limits(CATALOG_FIELD_LIMITS),
    )
}

fn validate(
    descriptor: &MessageDescriptor,
    bytes: &[u8],
    budget: ProtobufShapeBudget,
) -> Result<(), PayloadShapeError> {
    validate_message_shape(descriptor, bytes, budget, UnknownFieldPolicy::Skip)
}

fn fixed_descriptors() -> &'static FixedDescriptors {
    static DESCRIPTORS: OnceLock<FixedDescriptors> = OnceLock::new();
    DESCRIPTORS.get_or_init(|| {
        let pool = DescriptorPool::decode(descriptor_set_bytes())
            .expect("the build-generated protocol descriptor set must be valid");
        FixedDescriptors {
            manifest: required_message(&pool, MANIFEST_NAME),
            catalog: required_message(&pool, CATALOG_NAME),
            descriptor_set: required_message(&pool, DESCRIPTOR_SET_NAME),
        }
    })
}

fn required_message(pool: &DescriptorPool, name: &str) -> MessageDescriptor {
    pool.get_message_by_name(name)
        .unwrap_or_else(|| panic!("the protocol descriptor set must contain {name}"))
}

struct FixedDescriptors {
    manifest: MessageDescriptor,
    catalog: MessageDescriptor,
    descriptor_set: MessageDescriptor,
}
