use std::sync::Arc;

use async_trait::async_trait;
use reframe_store_protocol::wire::Envelope;
use reframe_store_runtime::{ResponseSink, ResponseSinkError, SemanticStoreRuntime, SessionOwner};
use reframe_store_transport::{ConnectionId, EnvelopeSender, Handler, HandlerError};

use crate::frame_policy::FramePolicy;

pub(crate) struct RuntimeHandler {
    frame_policy: FramePolicy,
    runtime: Arc<SemanticStoreRuntime>,
}

impl RuntimeHandler {
    pub(crate) const fn new(runtime: Arc<SemanticStoreRuntime>, frame_policy: FramePolicy) -> Self {
        Self {
            frame_policy,
            runtime,
        }
    }
}

#[async_trait]
impl Handler for RuntimeHandler {
    async fn handle(
        &self,
        mut envelope: Envelope,
        outbound: EnvelopeSender,
    ) -> Result<(), HandlerError> {
        self.frame_policy.constrain_request(&mut envelope);
        let owner = SessionOwner::new(outbound.connection_id().get());
        let sink: Arc<dyn ResponseSink> = Arc::new(TransportSink(outbound));
        self.runtime
            .dispatch_owned(owner, envelope, sink)
            .await
            .map_err(HandlerError::new)
    }

    async fn connection_closed(&self, connection_id: ConnectionId) {
        self.runtime
            .close_owner(SessionOwner::new(connection_id.get()))
            .await;
    }
}

struct TransportSink(EnvelopeSender);

#[async_trait]
impl ResponseSink for TransportSink {
    async fn send(&self, envelope: Envelope) -> Result<(), ResponseSinkError> {
        self.0
            .send(&envelope)
            .await
            .map_err(|error| ResponseSinkError::Rejected(error.to_string()))
    }

    async fn closed(&self) {
        self.0.closed().await;
    }
}
