use std::collections::HashMap;
use std::path::Path;

use anyhow::Result;

use crate::protocol::{MAX_FRAME_BYTES, Operation, ProtocolError, Request, Response};
use crate::store::Store;

use super::Daemon;
use super::framing::encode_response_with_limit;
use super::idempotency::IdempotencyAction;

const TERMINAL_FIELD_BYTES: usize = 128;

impl Daemon {
    pub(super) fn open_with_exclusive_ownership(root: &Path) -> Result<Self> {
        let mut store = Store::open(root)?;
        let removed = store.scavenge_orphan_blob_temporaries()?;
        if removed > 0 {
            eprintln!("[workspace-daemon] removed {removed} orphan blob temporary file(s)");
        }
        store.prune_protocol_history()?;
        Ok(Self {
            store,
            content_cache: Default::default(),
            residents: HashMap::new(),
            process_idempotency_requests: Default::default(),
            mounts: HashMap::new(),
        })
    }

    pub(super) fn handle(&mut self, request: Request) -> Response {
        if request.operation.mutates() {
            if let IdempotencyAction::Respond(response) = self.begin_idempotent(&request) {
                return transportable_response(&request, response, MAX_FRAME_BYTES).0;
            }
        }
        let result = self.execute(&request.operation);
        let response = match result {
            Ok(value) => Response {
                request_id: request.request_id.clone(),
                ok: true,
                result: Some(value),
                error: None,
            },
            Err(error) => failure(
                &request,
                crate::protocol::error_code::OPERATION_FAILED,
                &format!("{error:#}"),
            ),
        };
        self.finalize_response(&request, response, MAX_FRAME_BYTES)
    }

    pub(super) fn finalize_response(
        &self,
        request: &Request,
        response: Response,
        max_bytes: usize,
    ) -> Response {
        let (response, encoded_response) = transportable_response(request, response, max_bytes);
        if request.operation.mutates() {
            if let Some(key) = request.idempotency_key.as_deref() {
                if let Err(error) =
                    self.complete_idempotent(&request.operation, key, &encoded_response)
                {
                    let unknown = failure(
                        request,
                        crate::protocol::error_code::OUTCOME_UNKNOWN,
                        &format!(
                            "mutation finished but its durable outcome could not be recorded: {error}"
                        ),
                    );
                    return transportable_response(request, unknown, max_bytes).0;
                }
            }
        }
        response
    }
}

fn transportable_response(
    request: &Request,
    response: Response,
    max_bytes: usize,
) -> (Response, String) {
    match encode_response_with_limit(&response, max_bytes) {
        Ok(encoded) => (response, encoded),
        Err(error) => {
            let terminal = bounded_failure(
                request,
                crate::protocol::error_code::RESPONSE_TOO_LARGE,
                &format!("operation completed, but its response could not be transported: {error}"),
            );
            let encoded = encode_response_with_limit(&terminal, max_bytes)
                .expect("bounded protocol failure must fit in a response frame");
            (terminal, encoded)
        }
    }
}

pub(super) fn failure(request: &Request, code: &str, message: &str) -> Response {
    Response {
        request_id: request.request_id.clone(),
        ok: false,
        result: None,
        error: Some(ProtocolError {
            code: code.into(),
            operation: request.operation.name().into(),
            workspace_id: workspace_id(&request.operation),
            message: message.into(),
        }),
    }
}

fn bounded_failure(request: &Request, code: &str, message: &str) -> Response {
    Response {
        request_id: bounded(&request.request_id),
        ok: false,
        result: None,
        error: Some(ProtocolError {
            code: code.into(),
            operation: request.operation.name().into(),
            workspace_id: workspace_id(&request.operation).map(|value| bounded(&value)),
            message: message.into(),
        }),
    }
}

fn bounded(value: &str) -> String {
    if value.len() <= TERMINAL_FIELD_BYTES {
        return value.to_owned();
    }
    let mut end = TERMINAL_FIELD_BYTES;
    while !value.is_char_boundary(end) {
        end -= 1;
    }
    value[..end].to_owned()
}

fn workspace_id(operation: &Operation) -> Option<String> {
    match operation {
        Operation::ApplyPolicy { session_id, .. }
        | Operation::MountWorkspace { session_id }
        | Operation::Prefetch { session_id, .. }
        | Operation::GetChangeJournal { session_id }
        | Operation::GetWorkspaceStatus { session_id }
        | Operation::ReadFileSummary { session_id, .. }
        | Operation::CommitCheckpoint { session_id, .. }
        | Operation::UnmountWorkspace { session_id }
        | Operation::CloseWorkspace { session_id }
        | Operation::DestroyEphemeralWorkspace { session_id } => Some(session_id.clone()),
        _ => None,
    }
}
