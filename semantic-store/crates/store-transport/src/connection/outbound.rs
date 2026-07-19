use async_trait::async_trait;
use bytes::Bytes;
use prost::Message as _;
use reframe_store_protocol::wire::Envelope;
use std::sync::Arc;
use tokio::sync::{OwnedSemaphorePermit, Semaphore, TryAcquireError, mpsc};

use crate::{ConnectionId, FrameError, HandlerError, SendError, TrySendError, encode_envelope};

/// The only write path exposed to concurrent envelope handlers.
///
/// A bounded channel applies backpressure, and one connection-owned writer
/// serializes complete frames so concurrent responses cannot interleave.
#[derive(Clone, Debug)]
pub struct EnvelopeSender {
    connection_id: ConnectionId,
    sender: mpsc::Sender<OutboundFrame>,
    byte_budget: Arc<Semaphore>,
    aggregate_byte_budget: Arc<Semaphore>,
    maximum: usize,
}

impl EnvelopeSender {
    #[must_use]
    pub const fn connection_id(&self) -> ConnectionId {
        self.connection_id
    }

    pub async fn send(&self, envelope: &Envelope) -> Result<(), SendError> {
        let encoded_length = check_encoded_length(envelope, self.maximum)?;
        let queue_permit = self.sender.reserve().await.map_err(|_| SendError::Closed)?;
        let connection_permit = Arc::clone(&self.byte_budget)
            .acquire_many_owned(encoded_length)
            .await
            .map_err(|_| SendError::Closed)?;
        let aggregate_permit = tokio::select! {
            biased;
            () = self.sender.closed() => return Err(SendError::Closed),
            permit = Arc::clone(&self.aggregate_byte_budget)
                .acquire_many_owned(encoded_length) => {
                permit.map_err(|_| SendError::Closed)?
            }
        };
        queue_permit.send(OutboundFrame::new(
            encode_envelope(envelope, self.maximum)?,
            connection_permit,
            aggregate_permit,
        ));
        Ok(())
    }

    pub fn try_send(&self, envelope: &Envelope) -> Result<(), TrySendError> {
        let encoded_length = check_encoded_length(envelope, self.maximum)?;
        let queue_permit = self.sender.try_reserve().map_err(|error| match error {
            mpsc::error::TrySendError::Full(()) => TrySendError::Full,
            mpsc::error::TrySendError::Closed(()) => TrySendError::Closed,
        })?;
        let connection_permit = Arc::clone(&self.byte_budget)
            .try_acquire_many_owned(encoded_length)
            .map_err(|error| match error {
                TryAcquireError::NoPermits => TrySendError::Full,
                TryAcquireError::Closed => TrySendError::Closed,
            })?;
        let aggregate_permit = Arc::clone(&self.aggregate_byte_budget)
            .try_acquire_many_owned(encoded_length)
            .map_err(|error| match error {
                TryAcquireError::NoPermits => TrySendError::Full,
                TryAcquireError::Closed => TrySendError::Closed,
            })?;
        queue_permit.send(OutboundFrame::new(
            encode_envelope(envelope, self.maximum)?,
            connection_permit,
            aggregate_permit,
        ));
        Ok(())
    }

    #[must_use]
    pub fn is_closed(&self) -> bool {
        self.sender.is_closed()
    }

    #[must_use]
    pub fn capacity(&self) -> usize {
        self.sender.capacity()
    }

    #[cfg(test)]
    pub(super) fn available_byte_budget(&self) -> usize {
        self.byte_budget.available_permits()
    }

    /// Resolves when the connection-owned writer stops accepting responses.
    pub async fn closed(&self) {
        self.sender.closed().await;
    }
}

#[async_trait]
pub trait Handler: Send + Sync + 'static {
    /// Handles one envelope. Calls on the same connection may run concurrently.
    async fn handle(
        &self,
        envelope: Envelope,
        outbound: EnvelopeSender,
    ) -> Result<(), HandlerError>;

    /// Runs once after a connection can no longer dispatch or deliver frames.
    async fn connection_closed(&self, _connection_id: ConnectionId) {}
}

pub(super) fn channel(
    connection_id: ConnectionId,
    capacity: usize,
    byte_budget: usize,
    aggregate_byte_budget: Arc<Semaphore>,
    maximum: usize,
) -> (EnvelopeSender, OutboundReceiver) {
    let (sender, receiver) = mpsc::channel(capacity);
    let byte_budget = Arc::new(Semaphore::new(byte_budget));
    (
        EnvelopeSender {
            connection_id,
            sender,
            byte_budget: Arc::clone(&byte_budget),
            aggregate_byte_budget,
            maximum,
        },
        OutboundReceiver {
            receiver,
            byte_budget,
        },
    )
}

#[derive(Debug)]
pub(super) struct OutboundFrame {
    payload: Bytes,
    permits: OutboundPermits,
}

impl OutboundFrame {
    fn new(
        payload: Bytes,
        connection_permit: OwnedSemaphorePermit,
        aggregate_permit: OwnedSemaphorePermit,
    ) -> Self {
        debug_assert_eq!(payload.len(), connection_permit.num_permits());
        debug_assert_eq!(payload.len(), aggregate_permit.num_permits());
        Self {
            payload,
            permits: OutboundPermits {
                _connection: connection_permit,
                _aggregate: aggregate_permit,
            },
        }
    }

    pub(super) fn into_parts(self) -> (Bytes, OutboundPermits) {
        (self.payload, self.permits)
    }
}

#[derive(Debug)]
pub(super) struct OutboundPermits {
    _connection: OwnedSemaphorePermit,
    _aggregate: OwnedSemaphorePermit,
}

#[derive(Debug)]
pub(super) struct OutboundReceiver {
    receiver: mpsc::Receiver<OutboundFrame>,
    byte_budget: Arc<Semaphore>,
}

impl OutboundReceiver {
    pub(super) async fn recv(&mut self) -> Option<OutboundFrame> {
        self.receiver.recv().await
    }

    pub(super) fn close(&mut self) {
        self.receiver.close();
        self.byte_budget.close();
    }
}

impl Drop for OutboundReceiver {
    fn drop(&mut self) {
        self.byte_budget.close();
    }
}

fn check_encoded_length(envelope: &Envelope, maximum: usize) -> Result<u32, FrameError> {
    let actual = envelope.encoded_len();
    let encoded_length = u32::try_from(actual).map_err(|_| FrameError::LengthOverflow(actual))?;
    if actual > maximum {
        return Err(FrameError::TooLarge { actual, maximum });
    }
    Ok(encoded_length)
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use super::*;

    #[tokio::test]
    async fn bounded_queue_applies_backpressure() {
        let aggregate = Arc::new(Semaphore::new(1024));
        let (sender, mut receiver) = channel(ConnectionId::next(), 1, 1024, aggregate, 1024);
        let envelope = Envelope::default();
        sender.send(&envelope).await.unwrap();
        assert!(matches!(
            sender.try_send(&envelope),
            Err(TrySendError::Full)
        ));
        assert!(
            tokio::time::timeout(Duration::from_millis(20), sender.send(&envelope))
                .await
                .is_err()
        );

        receiver.recv().await.unwrap();
        sender.send(&envelope).await.unwrap();
    }

    #[tokio::test]
    async fn encoded_bytes_remain_reserved_until_the_writer_releases_the_frame() {
        let envelope = Envelope {
            request_id: "budgeted".repeat(8),
            ..Envelope::default()
        };
        let encoded_length = envelope.encoded_len();
        let aggregate = Arc::new(Semaphore::new(encoded_length));
        let (sender, mut receiver) = channel(
            ConnectionId::next(),
            4,
            encoded_length,
            aggregate,
            encoded_length,
        );

        sender.send(&envelope).await.unwrap();
        assert!(matches!(
            sender.try_send(&envelope),
            Err(TrySendError::Full)
        ));

        let frame_being_written = receiver.recv().await.unwrap();
        assert!(matches!(
            sender.try_send(&envelope),
            Err(TrySendError::Full)
        ));

        drop(frame_being_written);
        sender.try_send(&envelope).unwrap();
    }

    #[tokio::test]
    async fn aggregate_budget_is_shared_across_connection_queues() {
        let envelope = Envelope {
            request_id: "aggregate".repeat(8),
            ..Envelope::default()
        };
        let encoded_length = envelope.encoded_len();
        let aggregate = Arc::new(Semaphore::new(encoded_length));
        let (first, mut first_receiver) = channel(
            ConnectionId::next(),
            4,
            encoded_length,
            Arc::clone(&aggregate),
            encoded_length,
        );
        let (second, _second_receiver) = channel(
            ConnectionId::next(),
            4,
            encoded_length,
            Arc::clone(&aggregate),
            encoded_length,
        );

        first.send(&envelope).await.unwrap();
        assert!(matches!(
            second.try_send(&envelope),
            Err(TrySendError::Full)
        ));
        let frame_being_written = first_receiver.recv().await.unwrap();
        assert!(matches!(
            second.try_send(&envelope),
            Err(TrySendError::Full)
        ));

        drop(frame_being_written);
        second.try_send(&envelope).unwrap();
        assert_eq!(aggregate.available_permits(), 0);
    }
}
