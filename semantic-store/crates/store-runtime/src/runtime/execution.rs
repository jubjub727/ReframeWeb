use std::sync::{Arc, Weak, atomic::AtomicBool};

use reframe_store_catalog::{InvocationContract, InvocationMode as CatalogInvocationMode};
use reframe_store_protocol::wire::{
    CallFunctionRequest, ComponentInvocationRequest, ErrorCode, ReadResourceRequest,
    SubscribeResourceRequest, component_invocation_request,
};
use tokio::sync::{Mutex, oneshot};

use crate::{
    InvocationMode, ResponseSink,
    fault::ProtocolFault,
    invocation::{ActiveInvocation, InvocationOutput, run_invocation},
    session::Session,
};

use super::SemanticStoreRuntime;

pub(super) enum ExecutionRequest {
    Read(ReadResourceRequest),
    Subscribe(SubscribeResourceRequest),
    Call(CallFunctionRequest),
}

impl SemanticStoreRuntime {
    pub(super) async fn start_invocation(
        &self,
        session: &Arc<Session>,
        request_id: String,
        request: ExecutionRequest,
        sink: Arc<dyn ResponseSink>,
    ) -> Result<(), ProtocolFault> {
        let (component_request, contract) =
            execution_contract(session, request_id.clone(), request)?;
        component_request
            .validate()
            .map_err(|error| ProtocolFault::invalid_request(error.to_string()))?;
        let permit = Arc::clone(&self.invocation_slots)
            .try_acquire_owned()
            .map_err(|_| {
                ProtocolFault::new(
                    ErrorCode::RuntimeError,
                    "the runtime invocation limit has been reached",
                )
                .retryable()
            })?;

        let mode = match contract.mode() {
            CatalogInvocationMode::Unary => InvocationMode::Unary,
            CatalogInvocationMode::Subscription => InvocationMode::Subscription,
        };
        let finished = Arc::new(AtomicBool::new(false));
        let connection = Arc::clone(&sink);
        let output = Arc::new(Mutex::new(InvocationOutput::new(
            request_id.clone(),
            session.id.clone(),
            session.protocol,
            mode,
            sink,
            self.config.send_timeout(),
            Arc::clone(&finished),
        )));
        let (start, ready) = oneshot::channel();
        let task_output = Arc::clone(&output);
        let loaded = Arc::clone(&session.store);
        let weak_session = Arc::downgrade(session.state());
        let task_request_id = request_id.clone();
        let maximum_event_bytes = self.config.max_component_event_bytes();
        let task = tokio::spawn(async move {
            if ready.await.is_err() {
                finish_task(weak_session, &task_request_id).await;
                return;
            }
            tokio::select! {
                biased;
                () = connection.closed() => {
                    task_output.lock().await.abandon();
                }
                () = run_invocation(
                    loaded,
                    component_request,
                    contract,
                    &task_output,
                    maximum_event_bytes,
                ) => {}
            }
            finish_task(weak_session, &task_request_id).await;
        });
        let active = Arc::new(ActiveInvocation::new(output, task, finished, permit));
        if !session.try_add_invocation(
            request_id.clone(),
            Arc::clone(&active),
            self.config.max_invocations_per_session(),
        ) {
            active.abort_silent().await;
            let fault = if session.is_closed() {
                ProtocolFault::new(ErrorCode::SessionClosed, "the Store session is closed")
            } else {
                ProtocolFault::new(
                    ErrorCode::RuntimeError,
                    "the session invocation limit has been reached",
                )
                .retryable()
            };
            return Err(fault);
        }
        if start.send(()).is_err() {
            session.state().finish_invocation(&request_id).await;
            return Err(ProtocolFault::new(
                ErrorCode::RuntimeError,
                "invocation task did not start",
            )
            .retryable());
        }
        Ok(())
    }
}

fn execution_contract(
    session: &Session,
    request_id: String,
    request: ExecutionRequest,
) -> Result<(ComponentInvocationRequest, InvocationContract), ProtocolFault> {
    let (operation, contract) = match request {
        ExecutionRequest::Read(request) => {
            let selector = request.selector.as_ref().ok_or_else(|| {
                ProtocolFault::invalid_request("resource selector is missing")
                    .field("read_resource_request.selector", "is required")
            })?;
            let contract =
                session
                    .store
                    .catalog()
                    .validate_read(&request.resource_id, selector, false)?;
            (
                component_invocation_request::Operation::ReadResource(request),
                contract,
            )
        }
        ExecutionRequest::Subscribe(request) => {
            let selector = request.selector.as_ref().ok_or_else(|| {
                ProtocolFault::invalid_request("resource selector is missing")
                    .field("subscribe_resource_request.selector", "is required")
            })?;
            let contract =
                session
                    .store
                    .catalog()
                    .validate_read(&request.resource_id, selector, true)?;
            (
                component_invocation_request::Operation::SubscribeResource(request),
                contract,
            )
        }
        ExecutionRequest::Call(request) => {
            let input = request.input.as_ref().ok_or_else(|| {
                ProtocolFault::invalid_request("function input is missing")
                    .field("call_function_request.input", "is required")
            })?;
            let contract = session
                .store
                .catalog()
                .validate_call(&request.function_id, input)?;
            (
                component_invocation_request::Operation::CallFunction(request),
                contract,
            )
        }
    };
    Ok((
        ComponentInvocationRequest {
            request_id,
            operation: Some(operation),
        },
        contract,
    ))
}

async fn finish_task(session: Weak<crate::session::SessionState>, request_id: &str) {
    if let Some(session) = session.upgrade() {
        session.finish_invocation(request_id).await;
    }
}
