mod budget;
mod scanner;
mod wire;

use prost_reflect::MessageDescriptor;
use thiserror::Error;

/// Allocation-work limits applied before reflective protobuf decoding.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ProtobufShapeBudget {
    maximum_values: usize,
    maximum_depth: usize,
    maximum_messages: usize,
    repeated_field_limits: &'static [RepeatedFieldLimit],
}

impl ProtobufShapeBudget {
    #[must_use]
    pub const fn new(maximum_values: usize, maximum_depth: usize) -> Self {
        Self {
            maximum_values,
            maximum_depth,
            maximum_messages: maximum_values,
            repeated_field_limits: &[],
        }
    }

    /// Sets the maximum number of nested message occurrences in the payload.
    #[must_use]
    pub const fn with_maximum_messages(mut self, maximum_messages: usize) -> Self {
        self.maximum_messages = maximum_messages;
        self
    }

    /// Applies per-message-instance cardinality limits to repeated fields.
    #[must_use]
    pub const fn with_repeated_field_limits(
        mut self,
        limits: &'static [RepeatedFieldLimit],
    ) -> Self {
        self.repeated_field_limits = limits;
        self
    }
}

/// A decoded-element ceiling for one repeated field on each message instance.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RepeatedFieldLimit {
    pub message_full_name: &'static str,
    pub field_number: u32,
    pub maximum_values: usize,
}

/// Handling for protobuf fields not present in the trusted descriptor.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UnknownFieldPolicy {
    Reject,
    Skip,
}

/// Checks structural work without materializing strings, messages, lists, or maps.
pub fn validate_message_shape(
    descriptor: &MessageDescriptor,
    bytes: &[u8],
    limits: ProtobufShapeBudget,
    unknown_fields: UnknownFieldPolicy,
) -> Result<(), PayloadShapeError> {
    scanner::validate(descriptor, bytes, limits, unknown_fields)
}

/// A fixed-message structural validation failure.
#[derive(Debug, Error)]
#[non_exhaustive]
pub enum PayloadShapeError {
    #[error("payload protobuf wire data is malformed")]
    Decode(#[from] prost::DecodeError),
    #[error("payload contains fields absent from the declared message")]
    UnknownField,
    #[error("payload contains too many structural values")]
    ValueLimit,
    #[error("payload contains too many nested message values")]
    MessageLimit,
    #[error("payload repeated field exceeds its cardinality limit")]
    RepeatedFieldLimit,
    #[error("payload nesting exceeds its limit")]
    NestingLimit,
    #[error("payload field has an incompatible protobuf wire type")]
    WrongWireType,
    #[error("payload contains a malformed packed field")]
    MalformedPackedField,
    #[error("payload field is truncated")]
    TruncatedField,
    #[error("payload contains an unexpected group terminator")]
    UnexpectedEndGroup,
    #[error("payload contains an unterminated group")]
    UnterminatedGroup,
}
