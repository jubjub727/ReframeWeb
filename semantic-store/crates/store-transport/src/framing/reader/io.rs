use std::sync::Arc;
use std::time::Duration;

use bytes::{Bytes, BytesMut};
use reframe_store_protocol::wire::Envelope;
use tokio::io::{AsyncRead, AsyncReadExt};
use tokio::sync::{OwnedSemaphorePermit, Semaphore};
use tokio::time::Instant;

use super::{AdmittedEnvelope, FrameReader};
use crate::FrameError;
use crate::framing::{HEADER_SIZE, decode_envelope, validate_length};

impl<R> FrameReader<R>
where
    R: AsyncRead + Unpin,
{
    /// Returns `None` only for EOF before any byte of a new header.
    pub async fn read_frame(&mut self) -> Result<Option<Bytes>, FrameError> {
        Ok(self
            .read_frame_inner(None)
            .await?
            .map(|frame| frame.payload))
    }

    /// Bounds the time from a frame's first byte to its completion.
    /// Idle connections do not time out before a frame starts.
    pub async fn read_frame_with_timeout(
        &mut self,
        timeout: Duration,
    ) -> Result<Option<Bytes>, FrameError> {
        Ok(self
            .read_frame_inner(Some(timeout))
            .await?
            .map(|frame| frame.payload))
    }

    pub async fn read_envelope(&mut self) -> Result<Option<Envelope>, FrameError> {
        let Some(frame) = self.read_frame_inner(None).await? else {
            return Ok(None);
        };
        decode_envelope(frame.payload).map(Some)
    }

    pub async fn read_envelope_with_timeout(
        &mut self,
        timeout: Duration,
    ) -> Result<Option<Envelope>, FrameError> {
        let Some(frame) = self.read_frame_inner(Some(timeout)).await? else {
            return Ok(None);
        };
        decode_envelope(frame.payload).map(Some)
    }

    pub(crate) async fn read_admitted_envelope_with_timeout(
        &mut self,
        timeout: Duration,
    ) -> Result<Option<AdmittedEnvelope>, FrameError> {
        debug_assert!(self.inbound_budget.is_some());
        let Some(frame) = self.read_frame_inner(Some(timeout)).await? else {
            return Ok(None);
        };
        let envelope = decode_envelope(frame.payload)?;
        let permit = frame
            .permit
            .expect("an admission-budget reader always returns a permit");
        Ok(Some(AdmittedEnvelope::new(envelope, permit)))
    }

    async fn read_frame_inner(
        &mut self,
        timeout: Option<Duration>,
    ) -> Result<Option<AdmittedFrame>, FrameError> {
        if let Err(error) = self.start_deadline_if_partial(timeout) {
            self.reset_frame();
            return Err(error);
        }
        if let Err(error) = self.read_header(timeout).await {
            self.reset_frame();
            return Err(error);
        }
        if self.header_received == 0 {
            return Ok(None);
        }
        if let Err(error) = self.initialize_payload(timeout).await {
            self.reset_frame();
            return Err(error);
        }
        if let Err(error) = self.read_payload(timeout).await {
            self.reset_frame();
            return Err(error);
        }

        let payload = self.payload.take().expect("payload initialized").freeze();
        let permit = self.payload_permit.take();
        self.header_received = 0;
        self.payload_received = 0;
        self.frame_deadline = None;
        Ok(Some(AdmittedFrame { payload, permit }))
    }

    async fn read_header(&mut self, timeout: Option<Duration>) -> Result<(), FrameError> {
        while self.header_received < HEADER_SIZE {
            let received = read_with_deadline(
                &mut self.inner,
                &mut self.header[self.header_received..],
                self.frame_deadline,
                timeout,
            )
            .await?;
            if received == 0 {
                if self.header_received == 0 {
                    return Ok(());
                }
                return Err(FrameError::TruncatedHeader {
                    received: self.header_received,
                });
            }
            self.header_received += received;
            self.start_deadline_if_partial(timeout)?;
        }
        Ok(())
    }

    async fn initialize_payload(&mut self, timeout: Option<Duration>) -> Result<(), FrameError> {
        if self.payload.is_none() {
            let expected = u32::from_be_bytes(self.header) as usize;
            validate_length(expected, self.maximum)?;
            if let Some(budget) = self.inbound_budget.as_ref() {
                let permits =
                    u32::try_from(self.maximum).expect("the hard maximum frame size fits u32");
                self.payload_permit = Some(
                    acquire_with_deadline(
                        Arc::clone(budget),
                        permits,
                        self.frame_deadline,
                        timeout,
                    )
                    .await?,
                );
            }
            let mut payload = BytesMut::with_capacity(expected);
            payload.resize(expected, 0);
            self.payload = Some(payload);
        }
        Ok(())
    }

    fn reset_frame(&mut self) {
        self.header_received = 0;
        self.payload = None;
        self.payload_permit = None;
        self.payload_received = 0;
        self.frame_deadline = None;
    }

    async fn read_payload(&mut self, timeout: Option<Duration>) -> Result<(), FrameError> {
        let expected = self.payload.as_ref().map_or(0, BytesMut::len);
        while self.payload_received < expected {
            let payload = self.payload.as_mut().expect("payload initialized");
            let received = read_with_deadline(
                &mut self.inner,
                &mut payload[self.payload_received..],
                self.frame_deadline,
                timeout,
            )
            .await?;
            if received == 0 {
                return Err(FrameError::TruncatedPayload {
                    expected,
                    received: self.payload_received,
                });
            }
            self.payload_received += received;
        }
        Ok(())
    }

    fn start_deadline_if_partial(&mut self, timeout: Option<Duration>) -> Result<(), FrameError> {
        if self.frame_deadline.is_none()
            && (self.header_received > 0 || self.payload.is_some())
            && let Some(timeout) = timeout
        {
            self.frame_deadline = Some(
                Instant::now()
                    .checked_add(timeout)
                    .ok_or(FrameError::TimeoutOutOfRange { timeout })?,
            );
        }
        Ok(())
    }
}

struct AdmittedFrame {
    payload: Bytes,
    permit: Option<OwnedSemaphorePermit>,
}

async fn acquire_with_deadline(
    budget: Arc<Semaphore>,
    permits: u32,
    deadline: Option<Instant>,
    timeout: Option<Duration>,
) -> Result<OwnedSemaphorePermit, FrameError> {
    let acquire = budget.acquire_many_owned(permits);
    let result = if let (Some(deadline), Some(timeout)) = (deadline, timeout) {
        tokio::time::timeout_at(deadline, acquire)
            .await
            .map_err(|_elapsed| FrameError::ReadTimedOut { timeout })?
    } else {
        acquire.await
    };
    result.map_err(|_| FrameError::InboundBudgetClosed)
}

async fn read_with_deadline<R>(
    reader: &mut R,
    buffer: &mut [u8],
    deadline: Option<Instant>,
    timeout: Option<Duration>,
) -> Result<usize, FrameError>
where
    R: AsyncRead + Unpin,
{
    if let (Some(deadline), Some(timeout)) = (deadline, timeout) {
        tokio::time::timeout_at(deadline, reader.read(buffer))
            .await
            .map_err(|_elapsed| FrameError::ReadTimedOut { timeout })?
            .map_err(FrameError::from)
    } else {
        reader.read(buffer).await.map_err(FrameError::from)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::io::AsyncWriteExt as _;

    #[tokio::test]
    async fn header_waits_for_admission_before_allocating_payload() {
        const FRAME_LIMIT: usize = 16;

        let budget = Arc::new(Semaphore::new(FRAME_LIMIT));
        let held = Arc::clone(&budget)
            .acquire_many_owned(FRAME_LIMIT as u32)
            .await
            .unwrap();
        let (mut producer, consumer) = tokio::io::duplex(16);
        producer.write_all(&1_u32.to_be_bytes()).await.unwrap();
        let mut reader =
            FrameReader::with_inbound_budget(consumer, FRAME_LIMIT, Arc::clone(&budget));

        assert!(matches!(
            reader
                .read_admitted_envelope_with_timeout(Duration::from_millis(20))
                .await,
            Err(FrameError::ReadTimedOut { .. })
        ));
        assert!(reader.payload.is_none());
        assert!(reader.payload_permit.is_none());

        drop(held);
        assert_eq!(budget.available_permits(), FRAME_LIMIT);
    }

    #[tokio::test]
    async fn length_validation_precedes_admission_waiting() {
        const FRAME_LIMIT: usize = 16;

        let budget = Arc::new(Semaphore::new(FRAME_LIMIT));
        let _held = Arc::clone(&budget)
            .acquire_many_owned(FRAME_LIMIT as u32)
            .await
            .unwrap();
        let (mut producer, consumer) = tokio::io::duplex(16);
        producer
            .write_all(&((FRAME_LIMIT + 1) as u32).to_be_bytes())
            .await
            .unwrap();
        let mut reader = FrameReader::with_inbound_budget(consumer, FRAME_LIMIT, budget);

        assert!(matches!(
            reader
                .read_admitted_envelope_with_timeout(Duration::from_secs(1))
                .await,
            Err(FrameError::TooLarge {
                actual: 17,
                maximum: 16
            })
        ));
    }

    #[tokio::test]
    async fn payload_timeout_releases_its_admission_permit() {
        const FRAME_LIMIT: usize = 16;

        let budget = Arc::new(Semaphore::new(FRAME_LIMIT));
        let (mut producer, consumer) = tokio::io::duplex(16);
        producer.write_all(&1_u32.to_be_bytes()).await.unwrap();
        let mut reader =
            FrameReader::with_inbound_budget(consumer, FRAME_LIMIT, Arc::clone(&budget));

        assert!(matches!(
            reader
                .read_admitted_envelope_with_timeout(Duration::from_millis(20))
                .await,
            Err(FrameError::ReadTimedOut { .. })
        ));
        assert_eq!(budget.available_permits(), FRAME_LIMIT);
    }

    #[tokio::test]
    async fn zero_byte_frame_still_has_safe_admission_lifetime() {
        const FRAME_LIMIT: usize = 16;

        let budget = Arc::new(Semaphore::new(FRAME_LIMIT));
        let (mut producer, consumer) = tokio::io::duplex(16);
        producer.write_all(&0_u32.to_be_bytes()).await.unwrap();
        let mut reader =
            FrameReader::with_inbound_budget(consumer, FRAME_LIMIT, Arc::clone(&budget));

        let admitted = reader
            .read_admitted_envelope_with_timeout(Duration::from_secs(1))
            .await
            .unwrap()
            .unwrap();
        assert_eq!(budget.available_permits(), 0);
        let (envelope, permit) = admitted.into_parts();
        assert_eq!(envelope, Envelope::default());
        drop(permit);
        assert_eq!(budget.available_permits(), FRAME_LIMIT);
    }
}
