use std::error::Error;
use std::io;
use std::time::Duration;

use thiserror::Error;

#[derive(Debug, Error)]
pub enum ConfigError {
    #[error("maximum frame size must be between 1 and {maximum} bytes, got {actual}")]
    MaxFrameSize { actual: usize, maximum: usize },
    #[error("outbound channel capacity must be between 1 and {maximum}, got {actual}")]
    OutboundCapacity { actual: usize, maximum: usize },
    #[error(
        "outbound byte budget must be between the {minimum}-byte frame maximum and {maximum} bytes, got {actual}"
    )]
    OutboundByteBudget {
        actual: usize,
        minimum: usize,
        maximum: usize,
    },
    #[error(
        "aggregate outbound byte budget must be between the {minimum}-byte frame maximum and {maximum} bytes, got {actual}"
    )]
    AggregateOutboundByteBudget {
        actual: usize,
        minimum: usize,
        maximum: usize,
    },
    #[error(
        "inbound byte budget must be between the {minimum}-byte frame maximum and {maximum} bytes, got {actual}"
    )]
    InboundByteBudget {
        actual: usize,
        minimum: usize,
        maximum: usize,
    },
    #[error("maximum in-flight handler count must be between 1 and {maximum}, got {actual}")]
    MaxInFlight { actual: usize, maximum: usize },
    #[error("maximum connection count must be between 1 and {maximum}, got {actual}")]
    MaxConnections { actual: usize, maximum: usize },
    #[error("{name} must be non-zero and fit the platform monotonic clock")]
    Timeout { name: &'static str },
}

#[derive(Debug, Error)]
pub enum EndpointError {
    #[error("service name must contain 1 to 64 ASCII letters, digits, '.', '_' or '-' characters")]
    InvalidServiceName,
    #[cfg(unix)]
    #[error("Unix socket path contains an interior NUL byte")]
    InteriorNul,
    #[cfg(windows)]
    #[error("named pipe endpoint must use the local \\\\.\\pipe\\ namespace")]
    InvalidPipeName,
}

#[derive(Debug, Error)]
pub enum FrameError {
    #[error("transport I/O failed")]
    Io(#[from] io::Error),
    #[error("frame is {actual} bytes, exceeding the configured {maximum}-byte maximum")]
    TooLarge { actual: usize, maximum: usize },
    #[error("frame length {0} cannot be represented by the four-byte header")]
    LengthOverflow(usize),
    #[error("peer closed after {received} of 4 frame-header bytes")]
    TruncatedHeader { received: usize },
    #[error("peer closed after {received} of {expected} frame-payload bytes")]
    TruncatedPayload { expected: usize, received: usize },
    #[error("protobuf encoding failed")]
    Encode(#[from] prost::EncodeError),
    #[error("protobuf decoding failed")]
    Decode(#[from] prost::DecodeError),
    #[error("peer did not finish the current frame within {timeout:?}")]
    ReadTimedOut { timeout: Duration },
    #[error("peer did not accept the current frame within {timeout:?}")]
    WriteTimedOut { timeout: Duration },
    #[error("timeout {timeout:?} does not fit the platform monotonic clock")]
    TimeoutOutOfRange { timeout: Duration },
    #[error("frame writer cannot be reused after a partial or failed write")]
    WriterPoisoned,
    #[error("inbound frame admission budget has closed")]
    InboundBudgetClosed,
}

#[derive(Debug, Error)]
pub enum SendError {
    #[error(transparent)]
    Frame(#[from] FrameError),
    #[error("connection writer has closed")]
    Closed,
}

#[derive(Debug, Error)]
pub enum TrySendError {
    #[error(transparent)]
    Frame(#[from] FrameError),
    #[error("outbound queue is full")]
    Full,
    #[error("connection writer has closed")]
    Closed,
}

/// Type-erased error returned by an envelope handler.
#[derive(Debug)]
pub struct HandlerError(Box<dyn Error + Send + Sync + 'static>);

impl HandlerError {
    pub fn new(error: impl Error + Send + Sync + 'static) -> Self {
        Self(Box::new(error))
    }

    pub fn message(message: impl Into<String>) -> Self {
        Self::new(io::Error::other(message.into()))
    }
}

impl std::fmt::Display for HandlerError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        self.0.fmt(formatter)
    }
}

impl Error for HandlerError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        Some(self.0.as_ref())
    }
}

#[derive(Debug, Error)]
pub enum ConnectionError {
    #[error(transparent)]
    Frame(#[from] FrameError),
    #[error("envelope handler failed")]
    Handler(#[source] HandlerError),
    #[error("connection writer failed")]
    Writer(#[source] FrameError),
    #[error("connection task failed")]
    Task(#[source] tokio::task::JoinError),
    #[error("connection writer stopped unexpectedly")]
    WriterStopped,
    #[error("in-flight handlers did not finish within {timeout:?}")]
    HandlerDrainTimedOut { timeout: Duration },
}

#[derive(Debug, Error)]
pub enum ServerError {
    #[error("failed to accept a local connection")]
    Accept(#[source] io::Error),
    #[error("local connection task failed")]
    ConnectionTask(#[source] tokio::task::JoinError),
}
