use std::time::Duration;

use thiserror::Error;

use crate::ResponseSinkError;

/// A delivery failure after the runtime has accepted an envelope.
///
/// Client and Store mistakes are returned as protocol envelopes. This error is
/// reserved for a response destination that can no longer be written.
#[derive(Debug, Error)]
#[non_exhaustive]
pub enum DispatchError {
    #[error("response destination failed")]
    Sink(#[source] ResponseSinkError),
    #[error("response destination did not accept an envelope within {0:?}")]
    TimedOut(Duration),
}
