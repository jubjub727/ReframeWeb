use std::sync::Arc;

use super::{ConnectionId, Handler};

pub(super) struct ConnectionCleanup<H: Handler + ?Sized> {
    connection_id: ConnectionId,
    handler: Option<Arc<H>>,
}

impl<H: Handler + ?Sized> ConnectionCleanup<H> {
    pub(super) fn new(connection_id: ConnectionId, handler: Arc<H>) -> Self {
        Self {
            connection_id,
            handler: Some(handler),
        }
    }

    pub(super) async fn run(mut self) {
        let handler = self.handler.take().expect("cleanup runs only once");
        let connection_id = self.connection_id;
        let cleanup = tokio::spawn(async move {
            handler.connection_closed(connection_id).await;
        });
        if let Err(error) = cleanup.await {
            tracing::warn!(%error, ?connection_id, "connection cleanup task failed");
        }
    }
}

impl<H: Handler + ?Sized> Drop for ConnectionCleanup<H> {
    fn drop(&mut self) {
        let Some(handler) = self.handler.take() else {
            return;
        };
        let connection_id = self.connection_id;
        let Ok(runtime) = tokio::runtime::Handle::try_current() else {
            tracing::error!(?connection_id, "connection cleanup lost its Tokio runtime");
            return;
        };
        drop(runtime.spawn(async move {
            handler.connection_closed(connection_id).await;
        }));
    }
}
