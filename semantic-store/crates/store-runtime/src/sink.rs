use async_trait::async_trait;
use reframe_store_protocol::wire::Envelope;
use std::{sync::Arc, time::Duration};
use thiserror::Error;

use tokio::{sync::mpsc, time};

use crate::DispatchError;

/// Destination retained by asynchronous invocation tasks.
#[async_trait]
pub trait ResponseSink: Send + Sync + 'static {
    async fn send(&self, envelope: Envelope) -> Result<(), ResponseSinkError>;

    /// Resolves when future responses cannot reach the client.
    async fn closed(&self) {
        std::future::pending::<()>().await;
    }
}

/// Bounded channel sink useful to native embedders and tests.
#[derive(Debug, Clone)]
pub struct ChannelSink {
    sender: mpsc::Sender<Envelope>,
}

impl ChannelSink {
    #[must_use]
    pub const fn new(sender: mpsc::Sender<Envelope>) -> Self {
        Self { sender }
    }
}

#[async_trait]
impl ResponseSink for ChannelSink {
    async fn send(&self, envelope: Envelope) -> Result<(), ResponseSinkError> {
        self.sender
            .send(envelope)
            .await
            .map_err(|_| ResponseSinkError::Closed)
    }

    async fn closed(&self) {
        self.sender.closed().await;
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Error)]
pub enum ResponseSinkError {
    #[error("response destination is closed")]
    Closed,
    #[error("response destination rejected an envelope: {0}")]
    Rejected(String),
}

pub(crate) async fn send_bounded(
    sink: &Arc<dyn ResponseSink>,
    envelope: Envelope,
    timeout: Duration,
) -> Result<(), DispatchError> {
    match time::timeout(timeout, sink.send(envelope)).await {
        Ok(Ok(())) => Ok(()),
        Ok(Err(error)) => Err(DispatchError::Sink(error)),
        Err(_) => Err(DispatchError::TimedOut(timeout)),
    }
}
