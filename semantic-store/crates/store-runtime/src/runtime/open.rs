use std::sync::Arc;
use std::sync::atomic::Ordering;

use reframe_store_protocol::{
    CURRENT_PROTOCOL_VERSION,
    wire::{Envelope, ErrorCode, OpenStoreRequest, OpenStoreResponse, ProtocolVersion, envelope},
};

use crate::{
    ResponseSink, SessionOwner, fault::ProtocolFault, rollback::Rollback, session::Session,
    sink::send_bounded,
};

use super::{RouteError, SemanticStoreRuntime};

impl SemanticStoreRuntime {
    pub(super) async fn open_store(
        &self,
        owner: Option<SessionOwner>,
        envelope: &Envelope,
        request: OpenStoreRequest,
        sink: Arc<dyn ResponseSink>,
    ) -> Result<(), RouteError> {
        if self.shutting_down.load(Ordering::Acquire) {
            return Err(ProtocolFault::new(
                ErrorCode::RuntimeError,
                "the runtime is shutting down",
            )
            .retryable()
            .into());
        }
        if !envelope.session_id.is_empty() {
            return Err(ProtocolFault::invalid_request(
                "OpenStore must not carry an existing session ID",
            )
            .field("session_id", "must be empty for OpenStore")
            .into());
        }
        let loaded = self.registry.get(&request.store_id).ok_or_else(|| {
            ProtocolFault::new(ErrorCode::StoreNotFound, "requested Store is not installed")
        })?;
        let offered = request.supported_protocol_version.ok_or_else(|| {
            ProtocolFault::invalid_request("supported protocol version is missing")
        })?;
        let minimum = loaded
            .package()
            .manifest()
            .minimum_protocol_version
            .as_ref()
            .expect("verified manifests contain a minimum protocol version");
        let negotiated = negotiate_protocol(&offered, minimum)?;

        let required = request.required_interface.ok_or_else(|| {
            ProtocolFault::invalid_request("required semantic interface range is missing")
        })?;
        let interface = loaded
            .package()
            .manifest()
            .semantic_interface_version
            .as_ref()
            .expect("verified manifests contain an interface version");
        if !interface.satisfies(&required) {
            return Err(ProtocolFault::new(
                ErrorCode::InterfaceVersionMismatch,
                format!(
                    "installed interface {}.{} does not satisfy the requested range",
                    interface.major, interface.minor
                ),
            )
            .into());
        }

        let gate = self.session_gate.lock().await;
        if self.shutting_down.load(Ordering::Acquire) {
            return Err(ProtocolFault::new(
                ErrorCode::RuntimeError,
                "the runtime is shutting down",
            )
            .retryable()
            .into());
        }
        if self.sessions.len() >= self.config.max_sessions() {
            return Err(ProtocolFault::new(
                ErrorCode::RuntimeError,
                "the runtime session limit has been reached",
            )
            .retryable()
            .into());
        }
        let session_id = unique_session_id(&self.sessions);
        let session = Arc::new(Session::new(
            session_id.clone(),
            owner,
            negotiated,
            Arc::clone(&loaded),
            self.config.completion_history(),
        ));
        self.sessions
            .insert(session_id.clone(), Arc::clone(&session));
        drop(gate);

        let pending_session = Arc::clone(&session);
        let rollback = Rollback::new(|| {
            pending_session.close();
            self.sessions.remove_if(&session_id, |_, current| {
                Arc::ptr_eq(current, &pending_session)
            });
        });

        let response = Envelope {
            protocol_version: Some(negotiated),
            session_id: session_id.clone(),
            request_id: envelope.request_id.clone(),
            sequence_number: 0,
            message: Some(envelope::Message::OpenStoreResponse(OpenStoreResponse {
                store_id: request.store_id,
                negotiated_protocol_version: Some(negotiated),
                semantic_interface_version: Some(*interface),
                catalog_revision: loaded.package().catalog_revision().to_vec(),
            })),
        };
        send_bounded(&sink, response, self.config.send_timeout()).await?;
        rollback.disarm();
        Ok(())
    }
}

fn negotiate_protocol(
    offered: &ProtocolVersion,
    minimum: &ProtocolVersion,
) -> Result<ProtocolVersion, ProtocolFault> {
    if offered.major != CURRENT_PROTOCOL_VERSION.major {
        return Err(ProtocolFault::new(
            ErrorCode::UnsupportedProtocolVersion,
            format!(
                "client protocol {}.{} is incompatible with host protocol {}.{}",
                offered.major,
                offered.minor,
                CURRENT_PROTOCOL_VERSION.major,
                CURRENT_PROTOCOL_VERSION.minor
            ),
        ));
    }
    let negotiated = ProtocolVersion {
        major: CURRENT_PROTOCOL_VERSION.major,
        minor: negotiated_minor(offered.minor),
    };
    if !negotiated.supports(minimum) {
        return Err(ProtocolFault::new(
            ErrorCode::UnsupportedProtocolVersion,
            format!(
                "Store requires protocol {}.{}, but the negotiated version is {}.{}",
                minimum.major, minimum.minor, negotiated.major, negotiated.minor
            ),
        ));
    }
    Ok(negotiated)
}

#[allow(
    clippy::unnecessary_min_or_max,
    reason = "the host minor is zero today; this remains correct when the protocol advances"
)]
fn negotiated_minor(offered: u32) -> u32 {
    offered.min(CURRENT_PROTOCOL_VERSION.minor)
}

fn unique_session_id(sessions: &dashmap::DashMap<String, Arc<Session>>) -> String {
    loop {
        let candidate = uuid::Uuid::new_v4().to_string();
        if !sessions.contains_key(&candidate) {
            return candidate;
        }
    }
}
