use std::sync::Arc;

use reframe_store_protocol::wire::{
    CancelInvocationResponse, CancellationState, CloseStoreResponse, Envelope, ErrorCode,
    ProtocolVersion, envelope,
};

use crate::{
    ResponseSink, SessionOwner,
    fault::ProtocolFault,
    invocation::{ActiveInvocation, CancelDisposition},
    session::{Session, SessionState},
    sink::send_bounded,
};

use super::{RouteError, SemanticStoreRuntime, execution::ExecutionRequest};

impl SemanticStoreRuntime {
    pub(super) async fn route_session(
        &self,
        owner: Option<SessionOwner>,
        envelope: &Envelope,
        message: envelope::Message,
        sink: Arc<dyn ResponseSink>,
    ) -> Result<(), RouteError> {
        let session = self
            .sessions
            .get(&envelope.session_id)
            .map(|entry| Arc::clone(entry.value()))
            .ok_or_else(|| {
                ProtocolFault::new(
                    ErrorCode::InvalidSession,
                    "the Store session does not exist",
                )
            })?;
        if session.owner != owner {
            return Err(ProtocolFault::new(
                ErrorCode::InvalidSession,
                "the Store session does not exist",
            )
            .into());
        }
        require_negotiated_protocol(envelope.protocol_version.as_ref(), &session.protocol)?;
        if !session.begin_request(&envelope.request_id) {
            return Err(if session.is_closed() {
                ProtocolFault::new(ErrorCode::SessionClosed, "the Store session is closed")
            } else {
                ProtocolFault::request_conflict(&envelope.request_id)
            }
            .into());
        }
        let mut request_guard = RequestGuard::new(Arc::clone(&session), &envelope.request_id);

        let response = match message {
            envelope::Message::GetStoreCardRequest(request) => {
                envelope::Message::GetStoreCardResponse(
                    session.store.catalog().get_store_card(&request)?,
                )
            }
            envelope::Message::SearchCatalogRequest(request) => {
                envelope::Message::SearchCatalogResponse(
                    session.store.catalog().search_catalog(&request)?,
                )
            }
            envelope::Message::BrowseCatalogRequest(request) => {
                envelope::Message::BrowseCatalogResponse(
                    session.store.catalog().browse_catalog(&request)?,
                )
            }
            envelope::Message::InspectCapabilityRequest(request) => {
                envelope::Message::InspectCapabilityResponse(
                    session.store.catalog().inspect_capability(&request)?,
                )
            }
            envelope::Message::InspectTypeRequest(request) => {
                envelope::Message::InspectTypeResponse(
                    session.store.catalog().inspect_type(&request)?,
                )
            }
            envelope::Message::GetSchemaBundleRequest(request) => {
                envelope::Message::GetSchemaBundleResponse(
                    session.store.catalog().get_schema_bundle(&request)?,
                )
            }
            envelope::Message::ReadResourceRequest(request) => {
                self.start_invocation(
                    &session,
                    envelope.request_id.clone(),
                    ExecutionRequest::Read(request),
                    sink,
                )
                .await?;
                request_guard.disarm();
                return Ok(());
            }
            envelope::Message::SubscribeResourceRequest(request) => {
                self.start_invocation(
                    &session,
                    envelope.request_id.clone(),
                    ExecutionRequest::Subscribe(request),
                    sink,
                )
                .await?;
                request_guard.disarm();
                return Ok(());
            }
            envelope::Message::CallFunctionRequest(request) => {
                self.start_invocation(
                    &session,
                    envelope.request_id.clone(),
                    ExecutionRequest::Call(request),
                    sink,
                )
                .await?;
                request_guard.disarm();
                return Ok(());
            }
            envelope::Message::CancelInvocationRequest(request) => {
                let state = self.cancel_one(&session, &request.target_request_id).await;
                envelope::Message::CancelInvocationResponse(CancelInvocationResponse {
                    target_request_id: request.target_request_id,
                    state: state as i32,
                })
            }
            envelope::Message::CloseStoreRequest(_) => {
                let first_close = session.close();
                self.sessions.remove(&session.id);
                let cancellations = self.spawn_all_cancellations(&session);
                wait_for_cancellations(cancellations).await;
                envelope::Message::CloseStoreResponse(CloseStoreResponse {
                    closed: first_close,
                })
            }
            _ => {
                return Err(ProtocolFault::invalid_request(
                    "message is not valid for an open Store session",
                )
                .into());
            }
        };

        let reply = Envelope {
            protocol_version: Some(session.protocol),
            session_id: session.id.clone(),
            request_id: envelope.request_id.clone(),
            sequence_number: 0,
            message: Some(response),
        };
        send_bounded(&sink, reply, self.config.send_timeout()).await?;
        Ok(())
    }

    async fn cancel_one(&self, session: &Arc<Session>, request_id: &str) -> CancellationState {
        if let Some(invocation) = session.invocation(request_id) {
            match cancel_supervised(
                Arc::clone(session.state()),
                request_id.to_owned(),
                invocation,
            )
            .await
            {
                CancelDisposition::Cancelled => CancellationState::Cancelled,
                CancelDisposition::AlreadyFinished => CancellationState::AlreadyFinished,
            }
        } else if session.was_completed(request_id).await {
            CancellationState::AlreadyFinished
        } else {
            CancellationState::NotFound
        }
    }

    pub(super) fn spawn_all_cancellations(
        &self,
        session: &Arc<Session>,
    ) -> Vec<tokio::sync::oneshot::Receiver<CancelDisposition>> {
        let mut cancellations = Vec::new();
        for request_id in session.invocation_ids() {
            if let Some(invocation) = session.invocation(&request_id) {
                cancellations.push(spawn_cancellation(
                    Arc::clone(session.state()),
                    request_id,
                    invocation,
                ));
            }
        }
        cancellations
    }
}

async fn wait_for_cancellations(
    cancellations: Vec<tokio::sync::oneshot::Receiver<CancelDisposition>>,
) {
    for cancellation in cancellations {
        let _ = cancellation.await;
    }
}

async fn cancel_supervised(
    state: Arc<SessionState>,
    request_id: String,
    invocation: Arc<ActiveInvocation>,
) -> CancelDisposition {
    spawn_cancellation(state, request_id, invocation)
        .await
        .unwrap_or(CancelDisposition::AlreadyFinished)
}

fn spawn_cancellation(
    state: Arc<SessionState>,
    request_id: String,
    invocation: Arc<ActiveInvocation>,
) -> tokio::sync::oneshot::Receiver<CancelDisposition> {
    let (completed, result) = tokio::sync::oneshot::channel();
    drop(tokio::spawn(async move {
        let disposition = invocation.cancel().await;
        state.finish_invocation(&request_id).await;
        let _ = completed.send(disposition);
    }));
    result
}

fn require_negotiated_protocol(
    supplied: Option<&ProtocolVersion>,
    negotiated: &ProtocolVersion,
) -> Result<(), ProtocolFault> {
    if supplied == Some(negotiated) {
        Ok(())
    } else {
        Err(ProtocolFault::new(
            ErrorCode::UnsupportedProtocolVersion,
            format!(
                "session uses protocol {}.{}",
                negotiated.major, negotiated.minor
            ),
        ))
    }
}

struct RequestGuard {
    armed: bool,
    request_id: String,
    session: Arc<Session>,
}

impl RequestGuard {
    fn new(session: Arc<Session>, request_id: &str) -> Self {
        Self {
            armed: true,
            request_id: request_id.to_owned(),
            session,
        }
    }

    fn disarm(&mut self) {
        self.armed = false;
    }
}

impl Drop for RequestGuard {
    fn drop(&mut self) {
        if self.armed {
            self.session.finish_request(&self.request_id);
        }
    }
}

#[cfg(test)]
mod tests;
