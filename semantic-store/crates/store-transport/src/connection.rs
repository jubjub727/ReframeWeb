mod cleanup;
mod id;
#[cfg(test)]
mod inbound_tests;
mod outbound;
mod writer_task;

use std::sync::Arc;

use tokio::io::{AsyncRead, AsyncWrite};
use tokio::sync::Semaphore;
use tokio::task::{JoinError, JoinSet};
use tokio_util::sync::CancellationToken;

use crate::{ConnectionError, FrameReader, HandlerError, TransportConfig};

use cleanup::ConnectionCleanup;
pub use id::ConnectionId;
pub use outbound::{EnvelopeSender, Handler};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ConnectionEnd {
    /// The peer cleanly closed its sending half before a new frame.
    PeerClosed,
    /// The supplied cancellation token requested shutdown.
    Shutdown,
}

/// Drives one bidirectional stream until EOF, cancellation, or a fatal error.
pub async fn run_connection<S, H>(
    stream: S,
    handler: Arc<H>,
    config: TransportConfig,
    shutdown: CancellationToken,
) -> Result<ConnectionEnd, ConnectionError>
where
    S: AsyncRead + AsyncWrite + Unpin + Send + 'static,
    H: Handler + ?Sized,
{
    let inbound_budget = Arc::new(Semaphore::new(config.inbound_byte_budget()));
    let aggregate_outbound_budget =
        Arc::new(Semaphore::new(config.aggregate_outbound_byte_budget()));
    run_connection_with_shared_budgets(
        stream,
        handler,
        config,
        shutdown,
        inbound_budget,
        aggregate_outbound_budget,
    )
    .await
}

pub(crate) async fn run_connection_with_shared_budgets<S, H>(
    stream: S,
    handler: Arc<H>,
    config: TransportConfig,
    shutdown: CancellationToken,
    inbound_budget: Arc<Semaphore>,
    aggregate_outbound_budget: Arc<Semaphore>,
) -> Result<ConnectionEnd, ConnectionError>
where
    S: AsyncRead + AsyncWrite + Unpin + Send + 'static,
    H: Handler + ?Sized,
{
    let connection_id = ConnectionId::next();
    let connection_cleanup = ConnectionCleanup::new(connection_id, Arc::clone(&handler));
    let (read_half, write_half) = tokio::io::split(stream);
    let mut reader =
        FrameReader::with_inbound_budget(read_half, config.max_frame_size(), inbound_budget);
    let (outbound, outbound_rx) = outbound::channel(
        connection_id,
        config.outbound_capacity(),
        config.outbound_byte_budget(),
        aggregate_outbound_budget,
        config.max_frame_size(),
    );

    let writer_finished = CancellationToken::new();
    let writer_notice = writer_finished.clone();
    let writer_shutdown = CancellationToken::new();
    let writer_cancellation = writer_shutdown.clone();
    let maximum = config.max_frame_size();
    let write_timeout = config.write_timeout();
    let writer_task = tokio::spawn(async move {
        let _completion_notice = CompletionNotice(writer_notice);
        writer_task::run(
            write_half,
            outbound_rx,
            maximum,
            write_timeout,
            writer_cancellation,
        )
        .await
    });

    let mut handlers = JoinSet::new();
    let mut outcome = loop {
        if handlers.len() >= config.max_in_flight() {
            tokio::select! {
                biased;
                () = shutdown.cancelled() => break Ok(ConnectionEnd::Shutdown),
                () = writer_finished.cancelled() => break Err(ConnectionError::WriterStopped),
                completed = handlers.join_next() => {
                    if let Some(error) = completed.and_then(handler_completion_error) {
                        break Err(error);
                    }
                }
            }
            continue;
        }

        tokio::select! {
            biased;
            () = shutdown.cancelled() => break Ok(ConnectionEnd::Shutdown),
            () = writer_finished.cancelled() => break Err(ConnectionError::WriterStopped),
            completed = handlers.join_next(), if !handlers.is_empty() => {
                if let Some(error) = completed.and_then(handler_completion_error) {
                    break Err(error);
                }
            }
            admitted = reader.read_admitted_envelope_with_timeout(config.read_timeout()) => {
                match admitted {
                    Ok(Some(admitted)) => {
                        let (envelope, admission_permit) = admitted.into_parts();
                        let handler = Arc::clone(&handler);
                        let outbound = outbound.clone();
                        handlers.spawn(async move {
                            let result = handler.handle(envelope, outbound).await;
                            drop(admission_permit);
                            result
                        });
                    }
                    Ok(None) => break Ok(ConnectionEnd::PeerClosed),
                    Err(error) => break Err(ConnectionError::Frame(error)),
                }
            }
        }
    };
    // A cancelled read may have reserved admission bytes for a partial frame.
    // Release those immediately instead of retaining them while handlers and
    // the writer drain during connection shutdown.
    drop(reader);

    if outcome.is_ok() {
        let drain_timeout = config.handler_drain_timeout();
        let drain_deadline = tokio::time::sleep(drain_timeout);
        tokio::pin!(drain_deadline);
        while !handlers.is_empty() {
            tokio::select! {
                biased;
                () = writer_finished.cancelled() => {
                    outcome = Err(ConnectionError::WriterStopped);
                    handlers.abort_all();
                    break;
                }
                completed = handlers.join_next() => {
                    if let Some(error) = completed.and_then(handler_completion_error) {
                        outcome = Err(error);
                        handlers.abort_all();
                        break;
                    }
                }
                () = &mut drain_deadline => {
                    outcome = Err(ConnectionError::HandlerDrainTimedOut {
                        timeout: drain_timeout,
                    });
                    handlers.abort_all();
                    break;
                }
            }
        }
    } else {
        handlers.abort_all();
    }
    while handlers.join_next().await.is_some() {}

    // Stop accepting late responses once the read side and all dispatched
    // handlers are done. The writer drains frames already queued, then closes;
    // retained invocation senders observe a closed channel instead of keeping
    // the connection task alive indefinitely.
    writer_shutdown.cancel();
    drop(outbound);
    match writer_task.await {
        Ok(Ok(())) => {
            if matches!(outcome, Err(ConnectionError::WriterStopped)) {
                outcome = Err(ConnectionError::WriterStopped);
            }
        }
        Ok(Err(error)) => {
            if outcome.is_ok() || matches!(outcome, Err(ConnectionError::WriterStopped)) {
                outcome = Err(ConnectionError::Writer(error));
            }
        }
        Err(error) => {
            if outcome.is_ok() || matches!(outcome, Err(ConnectionError::WriterStopped)) {
                outcome = Err(ConnectionError::Task(error));
            }
        }
    }
    connection_cleanup.run().await;
    outcome
}

fn handler_completion_error(
    completed: Result<Result<(), HandlerError>, JoinError>,
) -> Option<ConnectionError> {
    match completed {
        Ok(Ok(())) => None,
        Ok(Err(error)) => Some(ConnectionError::Handler(error)),
        Err(error) => Some(ConnectionError::Task(error)),
    }
}

struct CompletionNotice(CancellationToken);

impl Drop for CompletionNotice {
    fn drop(&mut self) {
        self.0.cancel();
    }
}
