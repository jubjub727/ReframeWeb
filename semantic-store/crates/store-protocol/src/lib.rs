//! Canonical fixed protocol and package metadata types for Semantic Stores.

mod catalog_helpers;
#[cfg(feature = "reflection")]
mod payload_shape;
#[cfg(all(test, feature = "reflection"))]
mod payload_shape_tests;
mod validation;

mod generated {
    pub mod reframe {
        pub mod semantic_store {
            pub mod options {
                pub mod v1 {
                    include!(concat!(
                        env!("OUT_DIR"),
                        "/reframe.semantic_store.options.v1.rs"
                    ));
                }
            }

            pub mod types {
                pub mod v1 {
                    include!(concat!(
                        env!("OUT_DIR"),
                        "/reframe.semantic_store.types.v1.rs"
                    ));
                }
            }

            pub mod package {
                pub mod v1 {
                    include!(concat!(
                        env!("OUT_DIR"),
                        "/reframe.semantic_store.package.v1.rs"
                    ));
                }
            }

            pub mod v1 {
                include!(concat!(env!("OUT_DIR"), "/reframe.semantic_store.v1.rs"));
            }
        }
    }
}

/// Canonical protobuf method-option messages used by Store authors.
pub mod annotations {
    pub use crate::generated::reframe::semantic_store::options::v1::*;

    /// Fully-qualified `google.protobuf.MethodOptions` extension name.
    pub const CAPABILITY_OPTION_FULL_NAME: &str = "reframe.semantic_store.options.v1.capability";
    /// Globally assigned field number used by the method option.
    pub const CAPABILITY_OPTION_NUMBER: u32 = 51_000;
    /// Fully-qualified `google.protobuf.ServiceOptions` extension name.
    pub const STORE_SERVICE_OPTION_FULL_NAME: &str =
        "reframe.semantic_store.options.v1.store_service";
    /// Globally assigned field number used by the service option.
    pub const STORE_SERVICE_OPTION_NUMBER: u32 = 51_001;
    /// Import path Store-specific protobuf files should use.
    pub const PROTO_IMPORT: &str = "reframe/semantic_store/options/v1/annotations.proto";
}

/// Fixed transport envelopes and control messages.
pub mod wire {
    pub use crate::generated::reframe::semantic_store::types::v1::{
        InterfaceRequirement, InterfaceVersion, ProtocolVersion,
    };
    pub use crate::generated::reframe::semantic_store::v1::*;
}

/// Store package manifest and catalog messages.
pub mod package {
    pub use crate::generated::reframe::semantic_store::package::v1::*;
    pub use crate::generated::reframe::semantic_store::types::v1::{
        InterfaceVersion, ProtocolVersion,
    };
}

#[cfg(feature = "reflection")]
pub use payload_shape::{
    PayloadShapeError, ProtobufShapeBudget, RepeatedFieldLimit, UnknownFieldPolicy,
    validate_message_shape,
};
pub use validation::{
    CURRENT_PROTOCOL_VERSION, MAX_CAPABILITY_ID_BYTES, MAX_CURSOR_BYTES, MAX_FIELD_PATH_BYTES,
    MAX_FIELD_PATHS, MAX_IDEMPOTENCY_KEY_BYTES, MAX_INSPECTION_SECTIONS, MAX_QUERY_BYTES,
    MAX_REQUESTED_CAPABILITY_KINDS, MAX_TYPE_NAME_BYTES, MAX_TYPE_URL_BYTES, ValidationError,
    parse_uuid, validate_store_id, validate_uuid,
};

/// Include root containing the canonical Semantic Store annotation proto.
///
/// Downstream build scripts should add this path to protoc's include paths and
/// import `reframe/semantic_store/options/v1/annotations.proto`.
#[must_use]
pub fn annotation_proto_include_dir() -> &'static std::path::Path {
    std::path::Path::new(concat!(env!("CARGO_MANIFEST_DIR"), "/proto"))
}

/// The compiled descriptor set for the fixed Reframe protocol.
#[must_use]
pub const fn descriptor_set_bytes() -> &'static [u8] {
    include_bytes!(concat!(env!("OUT_DIR"), "/semantic_store_descriptor.bin"))
}
