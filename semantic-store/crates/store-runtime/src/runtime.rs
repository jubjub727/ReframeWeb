mod execution;
mod open;
mod reply;
mod session_routes;

use std::sync::{
    Arc,
    atomic::{AtomicBool, Ordering},
};

use dashmap::DashMap;
use reframe_store_protocol::{
    ValidationError,
    wire::{Envelope, ErrorCode, envelope},
};
use tokio::sync::{Mutex, Semaphore};

use crate::{
    DispatchError, ResponseSink, RuntimeConfig, SessionOwner, StoreRegistry, fault::ProtocolFault,
    session::Session, sink::send_bounded,
};

use self::reply::ReplyMetadata;

/// Concurrent, embeddable router for lifecycle, discovery, and execution.
pub struct SemanticStoreRuntime {
    config: RuntimeConfig,
    registry: Arc<StoreRegistry>,
    session_gate: Mutex<()>,
    sessions: DashMap<String, Arc<Session>>,
    shutting_down: AtomicBool,
    invocation_slots: Arc<Semaphore>,
}

impl std::fmt::Debug for SemanticStoreRuntime {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("SemanticStoreRuntime")
            .field("sessions", &self.sessions.len())
            .field("config", &self.config)
            .finish_non_exhaustive()
    }
}

impl SemanticStoreRuntime {
    #[must_use]
    pub fn new(registry: Arc<StoreRegistry>, config: RuntimeConfig) -> Self {
        let invocation_slots = Arc::new(Semaphore::new(config.max_active_invocations()));
        Self {
            config,
            invocation_slots,
            registry,
            session_gate: Mutex::new(()),
            sessions: DashMap::new(),
            shutting_down: AtomicBool::new(false),
        }
    }

    #[must_use]
    pub fn active_session_count(&self) -> usize {
        self.sessions.len()
    }

    #[must_use]
    pub const fn config(&self) -> &RuntimeConfig {
        &self.config
    }

    /// Routes one decoded request. Protocol failures are returned through the
    /// supplied sink; only response-delivery failures escape as Rust errors.
    pub async fn dispatch(
        &self,
        envelope: Envelope,
        sink: Arc<dyn ResponseSink>,
    ) -> Result<(), DispatchError> {
        self.dispatch_for_owner(None, envelope, sink).await
    }

    /// Routes one request on behalf of a connection-owned session namespace.
    /// Sessions opened here cannot be resumed from another owner.
    pub async fn dispatch_owned(
        &self,
        owner: SessionOwner,
        envelope: Envelope,
        sink: Arc<dyn ResponseSink>,
    ) -> Result<(), DispatchError> {
        self.dispatch_for_owner(Some(owner), envelope, sink).await
    }

    async fn dispatch_for_owner(
        &self,
        owner: Option<SessionOwner>,
        envelope: Envelope,
        sink: Arc<dyn ResponseSink>,
    ) -> Result<(), DispatchError> {
        let reply = ReplyMetadata::for_request(&envelope);
        if let Err(error) = envelope.validate() {
            let fault = validation_fault(error);
            return self.send_fault(&reply, fault, &sink).await;
        }

        match self.route(owner, envelope, Arc::clone(&sink)).await {
            Ok(()) => Ok(()),
            Err(RouteError::Protocol(fault)) => self.send_fault(&reply, fault, &sink).await,
            Err(RouteError::Delivery(error)) => Err(error),
        }
    }

    /// Closes every session created by one external connection. Removal from
    /// the routable session map is synchronous once the lifecycle gate is held;
    /// invocation cancellation is independently supervised.
    pub async fn close_owner(&self, owner: SessionOwner) {
        let gate = self.session_gate.lock().await;
        let sessions = self
            .sessions
            .iter()
            .filter(|entry| entry.owner == Some(owner))
            .map(|entry| Arc::clone(entry.value()))
            .collect::<Vec<_>>();
        for session in &sessions {
            session.close();
            self.sessions.remove(&session.id);
        }
        drop(gate);
        let cancellations = sessions
            .iter()
            .flat_map(|session| self.spawn_all_cancellations(session))
            .collect::<Vec<_>>();
        let cancellation = async {
            for cancellation in cancellations {
                let _ = cancellation.await;
            }
        };
        if tokio::time::timeout(self.config.shutdown_timeout(), cancellation)
            .await
            .is_err()
        {
            tracing::warn!(
                ?owner,
                timeout = ?self.config.shutdown_timeout(),
                "connection-owned session cleanup exceeded its deadline"
            );
        }
    }

    /// Hard-cancels every active invocation and releases every session.
    pub async fn shutdown(&self) {
        let gate = self.session_gate.lock().await;
        self.shutting_down.store(true, Ordering::Release);
        let sessions = self
            .sessions
            .iter()
            .map(|entry| Arc::clone(entry.value()))
            .collect::<Vec<_>>();
        drop(gate);
        for session in &sessions {
            session.close();
        }
        let cancellations = sessions
            .iter()
            .flat_map(|session| self.spawn_all_cancellations(session))
            .collect::<Vec<_>>();
        let graceful = async {
            for cancellation in cancellations {
                let _ = cancellation.await;
            }
        };
        if tokio::time::timeout(self.config.shutdown_timeout(), graceful)
            .await
            .is_err()
        {
            tracing::warn!(
                timeout = ?self.config.shutdown_timeout(),
                "Semantic Store shutdown exceeded its graceful deadline"
            );
        }
        for session in sessions {
            self.sessions.remove(&session.id);
        }
    }

    async fn route(
        &self,
        owner: Option<SessionOwner>,
        request: Envelope,
        sink: Arc<dyn ResponseSink>,
    ) -> Result<(), RouteError> {
        let message = request
            .message
            .clone()
            .ok_or_else(|| ProtocolFault::invalid_request("request message is missing"))?;
        match message {
            envelope::Message::OpenStoreRequest(open) => {
                self.open_store(owner, &request, open, sink).await
            }
            message if is_client_request(&message) => {
                self.route_session(owner, &request, message, sink).await
            }
            _ => Err(ProtocolFault::invalid_request(
                "clients may send only protocol request messages",
            )
            .into()),
        }
    }

    async fn send_fault(
        &self,
        reply: &ReplyMetadata,
        fault: ProtocolFault,
        sink: &Arc<dyn ResponseSink>,
    ) -> Result<(), DispatchError> {
        send_bounded(
            sink,
            reply.envelope(envelope::Message::Error(fault.into_message())),
            self.config.send_timeout(),
        )
        .await
    }
}

fn is_client_request(message: &envelope::Message) -> bool {
    matches!(
        message,
        envelope::Message::GetStoreCardRequest(_)
            | envelope::Message::SearchCatalogRequest(_)
            | envelope::Message::BrowseCatalogRequest(_)
            | envelope::Message::InspectCapabilityRequest(_)
            | envelope::Message::InspectTypeRequest(_)
            | envelope::Message::GetSchemaBundleRequest(_)
            | envelope::Message::ReadResourceRequest(_)
            | envelope::Message::SubscribeResourceRequest(_)
            | envelope::Message::CallFunctionRequest(_)
            | envelope::Message::CancelInvocationRequest(_)
            | envelope::Message::CloseStoreRequest(_)
    )
}

fn validation_fault(error: ValidationError) -> ProtocolFault {
    let code = if matches!(error, ValidationError::UnsupportedVersion { .. }) {
        ErrorCode::UnsupportedProtocolVersion
    } else {
        ErrorCode::InvalidEnvelope
    };
    ProtocolFault::new(code, error.to_string())
}

enum RouteError {
    Protocol(ProtocolFault),
    Delivery(DispatchError),
}

impl From<ProtocolFault> for RouteError {
    fn from(value: ProtocolFault) -> Self {
        Self::Protocol(value)
    }
}

impl From<DispatchError> for RouteError {
    fn from(value: DispatchError) -> Self {
        Self::Delivery(value)
    }
}

impl From<reframe_store_catalog::CatalogError> for RouteError {
    fn from(value: reframe_store_catalog::CatalogError) -> Self {
        Self::Protocol(ProtocolFault::from(value))
    }
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use reframe_store_protocol::{
        CURRENT_PROTOCOL_VERSION,
        wire::{Envelope, ErrorCode, InterfaceRequirement, OpenStoreRequest, envelope},
    };
    use tokio::sync::mpsc;

    use crate::{ChannelSink, EngineConfig, RuntimeEngine};

    use super::*;

    #[tokio::test]
    async fn unknown_store_is_a_correlated_protocol_error() {
        let engine = Arc::new(RuntimeEngine::new(EngineConfig::default()).unwrap());
        let registry = Arc::new(StoreRegistry::new(engine));
        let runtime = SemanticStoreRuntime::new(registry, RuntimeConfig::default());
        let request_id = uuid::Uuid::new_v4().to_string();
        let request = Envelope {
            protocol_version: Some(CURRENT_PROTOCOL_VERSION),
            request_id: request_id.clone(),
            message: Some(envelope::Message::OpenStoreRequest(OpenStoreRequest {
                store_id: "dev.reframe.missing".to_owned(),
                supported_protocol_version: Some(CURRENT_PROTOCOL_VERSION),
                required_interface: Some(InterfaceRequirement {
                    major: 1,
                    min_minor: 0,
                    max_minor: None,
                }),
            })),
            ..Envelope::default()
        };
        let (sender, mut receiver) = mpsc::channel(1);
        runtime
            .dispatch(request, Arc::new(ChannelSink::new(sender)))
            .await
            .unwrap();
        let response = receiver.recv().await.unwrap();
        assert_eq!(response.request_id, request_id);
        assert!(matches!(
            response.message,
            Some(envelope::Message::Error(error))
                if error.code == ErrorCode::StoreNotFound as i32
        ));
    }

    #[tokio::test]
    async fn shutdown_is_terminal_for_new_sessions() {
        let engine = Arc::new(RuntimeEngine::new(EngineConfig::default()).unwrap());
        let registry = Arc::new(StoreRegistry::new(engine));
        let runtime = SemanticStoreRuntime::new(registry, RuntimeConfig::default());
        runtime.shutdown().await;
        let request = Envelope {
            protocol_version: Some(CURRENT_PROTOCOL_VERSION),
            request_id: uuid::Uuid::new_v4().to_string(),
            message: Some(envelope::Message::OpenStoreRequest(OpenStoreRequest {
                store_id: "dev.reframe.example".to_owned(),
                supported_protocol_version: Some(CURRENT_PROTOCOL_VERSION),
                required_interface: Some(InterfaceRequirement {
                    major: 1,
                    min_minor: 0,
                    max_minor: None,
                }),
            })),
            ..Envelope::default()
        };
        let (sender, mut receiver) = mpsc::channel(1);
        runtime
            .dispatch(request, Arc::new(ChannelSink::new(sender)))
            .await
            .unwrap();
        assert!(matches!(
            receiver.recv().await.unwrap().message,
            Some(envelope::Message::Error(error))
                if error.code == ErrorCode::RuntimeError as i32 && error.retryable
        ));
    }
}
