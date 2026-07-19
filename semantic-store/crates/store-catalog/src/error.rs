use thiserror::Error;

/// Structured failures produced by catalog discovery and runtime validation.
#[derive(Debug, Clone, PartialEq, Eq, Error)]
#[non_exhaustive]
pub enum CatalogError {
    #[error("catalog is invalid: {reason}")]
    InvalidCatalog { reason: &'static str },
    #[error("capability {capability_id:?} was not found")]
    CapabilityNotFound { capability_id: String },
    #[error("topic {topic_id:?} was not found")]
    TopicNotFound { topic_id: String },
    #[error("type {type_name:?} was not found")]
    TypeNotFound { type_name: String },
    #[error("unknown capability kind value {value}")]
    InvalidCapabilityKind { value: i32 },
    #[error("unknown inspection section value {value}")]
    InvalidInspectionSection { value: i32 },
    #[error("field path {field_path:?} is invalid for type {type_name:?}")]
    InvalidFieldPath {
        type_name: String,
        field_path: String,
    },
    #[error("cursor is malformed, was modified, or belongs to another request")]
    InvalidCursor,
    #[error("cursor belongs to a different catalog revision")]
    StaleCursor,
    #[error("byte budget {budget} is invalid")]
    InvalidBudget { budget: u32 },
    #[error("byte budget {budget} cannot hold the next complete item ({required} bytes)")]
    BudgetExceeded { budget: usize, required: usize },
    #[error("capability {capability_id:?} is not a {expected}")]
    CapabilityKindMismatch {
        capability_id: String,
        expected: &'static str,
    },
    #[error("resource {capability_id:?} does not support subscriptions")]
    SubscriptionsUnsupported { capability_id: String },
    #[error("protobuf Any has invalid type URL {type_url:?}")]
    InvalidTypeUrl { type_url: String },
    #[error("protobuf Any declares {actual:?}; expected {expected:?}")]
    TypeMismatch { expected: String, actual: String },
    #[error("protobuf payload for {type_name:?} is invalid: {reason}")]
    InvalidPayload { type_name: String, reason: String },
    #[error("invocation contract belongs to another catalog revision")]
    ContractMismatch,
}
