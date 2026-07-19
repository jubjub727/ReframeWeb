mod io;

use bytes::BytesMut;
use std::sync::Arc;
use tokio::sync::{OwnedSemaphorePermit, Semaphore};
use tokio::time::Instant;

use super::HEADER_SIZE;
use crate::MAX_FRAME_SIZE;

/// A cancellation-safe reader for length-delimited frames.
///
/// Header and payload progress lives in the reader, so cancelling a
/// `read_frame` future never loses already-consumed bytes.
#[derive(Debug)]
pub struct FrameReader<R> {
    inner: R,
    maximum: usize,
    header: [u8; HEADER_SIZE],
    header_received: usize,
    payload: Option<BytesMut>,
    payload_permit: Option<OwnedSemaphorePermit>,
    inbound_budget: Option<Arc<Semaphore>>,
    payload_received: usize,
    frame_deadline: Option<Instant>,
}

impl<R> FrameReader<R> {
    #[must_use]
    pub fn new(inner: R, maximum: usize) -> Self {
        Self {
            inner,
            maximum: maximum.min(MAX_FRAME_SIZE),
            header: [0; HEADER_SIZE],
            header_received: 0,
            payload: None,
            payload_permit: None,
            inbound_budget: None,
            payload_received: 0,
            frame_deadline: None,
        }
    }

    pub(crate) fn with_inbound_budget(
        inner: R,
        maximum: usize,
        inbound_budget: Arc<Semaphore>,
    ) -> Self {
        Self {
            inbound_budget: Some(inbound_budget),
            ..Self::new(inner, maximum)
        }
    }

    #[must_use]
    pub const fn maximum(&self) -> usize {
        self.maximum
    }

    #[must_use]
    pub fn get_ref(&self) -> &R {
        &self.inner
    }

    pub fn get_mut(&mut self) -> &mut R {
        &mut self.inner
    }

    #[must_use]
    pub fn into_inner(self) -> R {
        self.inner
    }
}

pub(crate) struct AdmittedEnvelope {
    envelope: reframe_store_protocol::wire::Envelope,
    _permit: OwnedSemaphorePermit,
}

impl AdmittedEnvelope {
    pub(crate) fn new(
        envelope: reframe_store_protocol::wire::Envelope,
        permit: OwnedSemaphorePermit,
    ) -> Self {
        Self {
            envelope,
            _permit: permit,
        }
    }

    pub(crate) fn into_parts(
        self,
    ) -> (reframe_store_protocol::wire::Envelope, OwnedSemaphorePermit) {
        (self.envelope, self._permit)
    }
}
