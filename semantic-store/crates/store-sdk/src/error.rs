use reframe_store_protocol::{ValidationError, wire::FailureCode};
use thiserror::Error;

#[derive(Debug, Error)]
#[non_exhaustive]
pub enum AnyError {
    #[error("invalid protobuf Any type URL")]
    InvalidTypeUrl,
    #[error("invalid protobuf message name {0:?}")]
    InvalidTypeName(String),
    #[error("protobuf Any contains {actual:?}; expected {expected:?}")]
    TypeMismatch { expected: String, actual: String },
    #[error("invalid protobuf payload: {0}")]
    Decode(#[source] prost::DecodeError),
}

#[derive(Debug, Error)]
#[non_exhaustive]
pub enum RequestError {
    #[error("request bytes are not a ComponentInvocationRequest: {0}")]
    Decode(#[source] prost::DecodeError),
    #[error("invalid component invocation request: {0}")]
    Invalid(#[source] ValidationError),
    #[error("component invocation request has no operation")]
    MissingOperation,
    #[error(transparent)]
    Input(#[from] AnyError),
}

#[derive(Debug, Error)]
#[non_exhaustive]
pub enum EventError {
    #[error("invalid invocation request ID: {0}")]
    InvalidRequestId(#[source] ValidationError),
    #[error("a unary invocation may contain exactly one Data event")]
    UnaryCardinality,
    #[error("failure code must not be unspecified")]
    UnspecifiedFailureCode,
    #[error("progress total {total} is less than completed value {completed}")]
    InvalidProgress { completed: u64, total: u64 },
    #[error("invocation sequence number overflowed")]
    SequenceOverflow,
    #[error("invocation event cannot be encoded: {0}")]
    Encode(#[source] prost::EncodeError),
    #[error("invocation is already being polled")]
    ReentrantPoll,
    #[error(transparent)]
    Value(#[from] AnyError),
}

/// A stable, non-debug error suitable for the WIT `string` error channel.
#[derive(Debug, Error)]
#[non_exhaustive]
pub enum GuestError {
    #[error("invalid request: {0}")]
    InvalidRequest(#[from] RequestError),
    #[error("invalid invocation events: {0}")]
    InvalidEvents(#[from] EventError),
    #[error("invalid input: {0}")]
    InvalidInput(String),
    #[error("Store implementation error: {0}")]
    Internal(String),
}

impl GuestError {
    /// Converts the error to the fixed WIT boundary representation.
    #[must_use]
    pub fn into_wit_string(self) -> String {
        self.to_string()
    }
}

pub(crate) fn validate_failure_code(code: FailureCode) -> Result<(), EventError> {
    if code == FailureCode::Unspecified {
        Err(EventError::UnspecifiedFailureCode)
    } else {
        Ok(())
    }
}
