use reframe_store_protocol::wire::FailureCode;
use thiserror::Error;

#[derive(Debug, Error)]
#[non_exhaustive]
pub enum ResourceError {
    #[error("{0}")]
    InvalidInput(String),
    #[error("{0}")]
    Unavailable(String),
    #[error("{0}")]
    ResponseTooLarge(String),
}

impl ResourceError {
    pub(crate) const fn failure_code(&self) -> FailureCode {
        match self {
            Self::InvalidInput(_) | Self::ResponseTooLarge(_) => FailureCode::InvalidArgument,
            Self::Unavailable(_) => FailureCode::Unavailable,
        }
    }

    pub(crate) const fn retryable(&self) -> bool {
        matches!(self, Self::Unavailable(_))
    }
}
