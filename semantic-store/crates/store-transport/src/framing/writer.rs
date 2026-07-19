use std::time::Duration;

use reframe_store_protocol::wire::Envelope;
use tokio::io::{AsyncWrite, AsyncWriteExt};
use tokio::time::Instant;

use super::{encode_envelope, validate_length};
use crate::{FrameError, MAX_FRAME_SIZE};

#[derive(Debug)]
pub struct FrameWriter<W> {
    inner: W,
    maximum: usize,
    poisoned: bool,
}

impl<W> FrameWriter<W> {
    #[must_use]
    pub const fn new(inner: W, maximum: usize) -> Self {
        Self {
            inner,
            maximum: if maximum > MAX_FRAME_SIZE {
                MAX_FRAME_SIZE
            } else {
                maximum
            },
            poisoned: false,
        }
    }

    #[must_use]
    pub fn get_ref(&self) -> &W {
        &self.inner
    }

    pub fn get_mut(&mut self) -> &mut W {
        &mut self.inner
    }

    #[must_use]
    pub const fn is_poisoned(&self) -> bool {
        self.poisoned
    }

    #[must_use]
    pub fn into_inner(self) -> W {
        self.inner
    }
}

impl<W> FrameWriter<W>
where
    W: AsyncWrite + Unpin,
{
    pub async fn write_frame(&mut self, payload: impl AsRef<[u8]>) -> Result<(), FrameError> {
        let payload = payload.as_ref();
        validate_length(payload.len(), self.maximum)?;
        if self.poisoned {
            return Err(FrameError::WriterPoisoned);
        }
        let length =
            u32::try_from(payload.len()).map_err(|_| FrameError::LengthOverflow(payload.len()))?;
        let result = async {
            self.inner.write_all(&length.to_be_bytes()).await?;
            self.inner.write_all(payload).await
        }
        .await;
        if result.is_err() {
            self.poisoned = true;
        }
        result.map_err(FrameError::from)
    }

    pub async fn write_envelope(&mut self, envelope: &Envelope) -> Result<(), FrameError> {
        let payload = encode_envelope(envelope, self.maximum)?;
        self.write_frame(payload).await
    }

    pub async fn write_frame_with_timeout(
        &mut self,
        payload: impl AsRef<[u8]>,
        timeout: Duration,
    ) -> Result<(), FrameError> {
        let deadline = deadline(timeout)?;
        match tokio::time::timeout_at(deadline, self.write_frame(payload)).await {
            Ok(result) => result,
            Err(_elapsed) => {
                self.poisoned = true;
                Err(FrameError::WriteTimedOut { timeout })
            }
        }
    }

    pub async fn write_envelope_with_timeout(
        &mut self,
        envelope: &Envelope,
        timeout: Duration,
    ) -> Result<(), FrameError> {
        let payload = encode_envelope(envelope, self.maximum)?;
        self.write_frame_with_timeout(payload, timeout).await
    }

    pub async fn flush(&mut self) -> Result<(), FrameError> {
        self.inner.flush().await.map_err(FrameError::from)
    }

    pub async fn flush_with_timeout(&mut self, timeout: Duration) -> Result<(), FrameError> {
        tokio::time::timeout_at(deadline(timeout)?, self.flush())
            .await
            .map_err(|_elapsed| FrameError::WriteTimedOut { timeout })?
    }

    pub async fn shutdown(&mut self) -> Result<(), FrameError> {
        self.inner.shutdown().await.map_err(FrameError::from)
    }

    pub async fn shutdown_with_timeout(&mut self, timeout: Duration) -> Result<(), FrameError> {
        tokio::time::timeout_at(deadline(timeout)?, self.shutdown())
            .await
            .map_err(|_elapsed| FrameError::WriteTimedOut { timeout })?
    }
}

fn deadline(timeout: Duration) -> Result<Instant, FrameError> {
    Instant::now()
        .checked_add(timeout)
        .ok_or(FrameError::TimeoutOutOfRange { timeout })
}
