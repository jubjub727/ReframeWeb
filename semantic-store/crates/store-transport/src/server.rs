use std::sync::Arc;

use tokio::sync::Semaphore;
use tokio::task::{JoinError, JoinSet};
use tokio_util::sync::CancellationToken;

use crate::connection::run_connection_with_shared_budgets;
use crate::{ConnectionEnd, ConnectionError, Handler, LocalListener, ServerError, TransportConfig};

/// Accepts and drives local connections until `shutdown` is cancelled.
///
/// Connection-level protocol, I/O, and handler errors terminate only the
/// affected connection. Listener failures and task panics terminate the server.
pub async fn serve_local<H>(
    mut listener: LocalListener,
    handler: Arc<H>,
    config: TransportConfig,
    shutdown: CancellationToken,
) -> Result<(), ServerError>
where
    H: Handler + ?Sized,
{
    let connection_shutdown = shutdown.child_token();
    let inbound_budget = Arc::new(Semaphore::new(config.inbound_byte_budget()));
    let aggregate_outbound_budget =
        Arc::new(Semaphore::new(config.aggregate_outbound_byte_budget()));
    let mut connections = JoinSet::new();
    let mut outcome = loop {
        if connections.len() >= config.max_connections() {
            tokio::select! {
                biased;
                () = shutdown.cancelled() => break Ok(()),
                completed = connections.join_next() => {
                    if let Some(error) = completed.and_then(connection_task_error) {
                        break Err(error);
                    }
                }
            }
            continue;
        }

        tokio::select! {
            biased;
            () = shutdown.cancelled() => break Ok(()),
            completed = connections.join_next(), if !connections.is_empty() => {
                if let Some(error) = completed.and_then(connection_task_error) {
                    break Err(error);
                }
            }
            accepted = listener.accept() => {
                match accepted {
                    Ok(stream) => {
                        let handler = Arc::clone(&handler);
                        let config = config.clone();
                        let shutdown = connection_shutdown.child_token();
                        let inbound_budget = Arc::clone(&inbound_budget);
                        let aggregate_outbound_budget = Arc::clone(&aggregate_outbound_budget);
                        connections.spawn(async move {
                            run_connection_with_shared_budgets(
                                stream,
                                handler,
                                config,
                                shutdown,
                                inbound_budget,
                                aggregate_outbound_budget,
                            )
                            .await
                        });
                    }
                    Err(error) => break Err(ServerError::Accept(error)),
                }
            }
        }
    };

    connection_shutdown.cancel();
    while let Some(completed) = connections.join_next().await {
        if let Some(error) = connection_task_error(completed)
            && outcome.is_ok()
        {
            outcome = Err(error);
        }
    }
    outcome
}

fn connection_task_error(
    completed: Result<Result<ConnectionEnd, ConnectionError>, JoinError>,
) -> Option<ServerError> {
    match completed {
        Ok(Ok(end)) => {
            tracing::debug!(?end, "local Semantic Store connection closed");
            None
        }
        Ok(Err(error)) => {
            tracing::warn!(%error, "local Semantic Store connection failed");
            None
        }
        Err(error) => Some(ServerError::ConnectionTask(error)),
    }
}
