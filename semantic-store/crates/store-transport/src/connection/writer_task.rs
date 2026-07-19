use std::time::Duration;

use tokio::io::AsyncWrite;
use tokio_util::sync::CancellationToken;

use super::outbound::OutboundReceiver;
use crate::{FrameError, FrameWriter};

pub(super) async fn run<W>(
    write_half: W,
    mut outbound: OutboundReceiver,
    maximum: usize,
    write_timeout: Duration,
    shutdown: CancellationToken,
) -> Result<(), FrameError>
where
    W: AsyncWrite + Unpin,
{
    let mut writer = FrameWriter::new(write_half, maximum);
    let mut close_and_drain = false;
    loop {
        tokio::select! {
            biased;
            () = shutdown.cancelled() => {
                outbound.close();
                close_and_drain = true;
                break;
            },
            frame = outbound.recv() => {
                let Some(frame) = frame else {
                    break;
                };
                let (payload, budget_permits) = frame.into_parts();
                // Once a frame starts it either completes or times out. We
                // never cancel it and resume writing a later frame.
                writer
                    .write_frame_with_timeout(payload, write_timeout)
                    .await?;
                drop(budget_permits);
            }
        }
    }
    if close_and_drain {
        tokio::time::timeout(write_timeout, async {
            while let Some(frame) = outbound.recv().await {
                let (payload, budget_permits) = frame.into_parts();
                writer
                    .write_frame_with_timeout(payload, write_timeout)
                    .await?;
                drop(budget_permits);
            }
            Ok::<_, FrameError>(())
        })
        .await
        .map_err(|_| FrameError::WriteTimedOut {
            timeout: write_timeout,
        })??;
    }
    writer.flush_with_timeout(write_timeout).await?;
    writer.shutdown_with_timeout(write_timeout).await
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;
    use std::time::Duration;

    use prost::Message as _;
    use reframe_store_protocol::wire::Envelope;
    use tokio::io::{AsyncReadExt as _, duplex};
    use tokio_util::sync::CancellationToken;

    use super::*;
    use crate::ConnectionId;
    use crate::connection::outbound::channel;

    #[tokio::test]
    async fn byte_permit_is_released_only_after_the_frame_write_finishes() {
        let envelope = Envelope {
            request_id: "writer-budget".repeat(8),
            ..Envelope::default()
        };
        let encoded_length = envelope.encoded_len();
        let aggregate = Arc::new(tokio::sync::Semaphore::new(encoded_length));
        let (sender, outbound) = channel(
            ConnectionId::next(),
            4,
            encoded_length,
            aggregate,
            encoded_length,
        );
        sender.send(&envelope).await.unwrap();

        let (write_half, mut read_half) = duplex(1);
        let writer = tokio::spawn(run(
            write_half,
            outbound,
            encoded_length,
            Duration::from_secs(1),
            CancellationToken::new(),
        ));

        let mut first_byte = [0_u8; 1];
        read_half.read_exact(&mut first_byte).await.unwrap();
        assert_eq!(sender.available_byte_budget(), 0);

        let mut remainder = vec![0_u8; 4 + encoded_length - first_byte.len()];
        read_half.read_exact(&mut remainder).await.unwrap();
        tokio::time::timeout(Duration::from_secs(1), async {
            while sender.available_byte_budget() != encoded_length {
                tokio::task::yield_now().await;
            }
        })
        .await
        .expect("finishing the write must release its byte permit");

        drop(sender);
        writer.await.unwrap().unwrap();
    }
}
