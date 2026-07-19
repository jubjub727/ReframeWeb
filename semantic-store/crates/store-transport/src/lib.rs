//! Length-delimited protobuf transport for local Semantic Store connections.
//!
//! Frames are a four-byte big-endian payload length followed by one encoded
//! [`reframe_store_protocol::wire::Envelope`]. [`FrameReader`] retains partial
//! progress across cancellation. [`run_connection`] bounds dispatch and sends
//! all responses through one frame writer, preserving frame atomicity while
//! applying backpressure. Every connection has a process-local [`ConnectionId`]
//! and runs [`Handler::connection_closed`] exactly once, including when its
//! driver future is cancelled.

#![deny(unsafe_code)]

mod config;
mod connection;
mod endpoint;
mod error;
mod framing;
mod local;
mod server;

pub use config::{
    DEFAULT_AGGREGATE_OUTBOUND_BYTE_BUDGET, DEFAULT_HANDLER_DRAIN_TIMEOUT,
    DEFAULT_INBOUND_BYTE_BUDGET, DEFAULT_MAX_CONNECTIONS, DEFAULT_MAX_FRAME_SIZE,
    DEFAULT_MAX_IN_FLIGHT, DEFAULT_OUTBOUND_BYTE_BUDGET, DEFAULT_OUTBOUND_CAPACITY,
    DEFAULT_READ_TIMEOUT, DEFAULT_WRITE_TIMEOUT, MAX_CONNECTIONS, MAX_FRAME_SIZE, MAX_IN_FLIGHT,
    MAX_OUTBOUND_CAPACITY, TransportConfig,
};
pub use connection::{ConnectionEnd, ConnectionId, EnvelopeSender, Handler, run_connection};
pub use endpoint::{DEFAULT_SERVICE_NAME, LocalEndpoint};
pub use error::{
    ConfigError, ConnectionError, EndpointError, FrameError, HandlerError, SendError, ServerError,
    TrySendError,
};
pub use framing::{
    FrameReader, FrameWriter, decode_envelope, decode_message, encode_envelope, encode_frame,
    encode_message, read_envelope, read_frame, write_envelope, write_frame,
};
pub use local::{
    DEFAULT_CONNECT_TIMEOUT, LocalListener, LocalStream, connect, connect_with_timeout,
};
pub use server::serve_local;
