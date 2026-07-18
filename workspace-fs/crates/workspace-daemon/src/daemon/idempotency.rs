use std::collections::{HashMap, VecDeque};

use anyhow::{Result, bail};

use crate::protocol::{IdempotencyScope, Operation, Request, Response};
use crate::store::IdempotencyReservation;

use super::Daemon;
use super::server::failure;

pub(super) enum IdempotencyAction {
    Execute,
    Respond(Response),
}

const PROCESS_IDEMPOTENCY_CAPACITY: usize = 4096;

struct ProcessIdempotencyRequest {
    operation: String,
    request_hash: String,
}

#[derive(Default)]
pub(super) struct ProcessIdempotencyRequests {
    entries: HashMap<String, ProcessIdempotencyRequest>,
    insertion_order: VecDeque<String>,
}

impl ProcessIdempotencyRequests {
    fn get(&self, key: &str) -> Option<&ProcessIdempotencyRequest> {
        self.entries.get(key)
    }

    fn insert(&mut self, key: String, operation: String, request_hash: String) {
        while self.entries.len() >= PROCESS_IDEMPOTENCY_CAPACITY {
            let Some(oldest) = self.insertion_order.pop_front() else {
                self.entries.clear();
                break;
            };
            self.entries.remove(&oldest);
        }
        self.entries.insert(
            key.clone(),
            ProcessIdempotencyRequest {
                operation,
                request_hash,
            },
        );
        self.insertion_order.push_back(key);
    }
}

impl Daemon {
    pub(super) fn begin_idempotent(&mut self, request: &Request) -> IdempotencyAction {
        let Some(key) = request.idempotency_key.as_deref() else {
            return IdempotencyAction::Respond(failure(
                request,
                crate::protocol::error_code::IDEMPOTENCY_REQUIRED,
                "mutating operations require idempotency_key",
            ));
        };
        let request_hash = match operation_hash(&request.operation) {
            Ok(hash) => hash,
            Err(error) => {
                return IdempotencyAction::Respond(failure(
                    request,
                    crate::protocol::error_code::IDEMPOTENCY_ERROR,
                    &format!("could not hash idempotent request: {error}"),
                ));
            }
        };
        match request.operation.idempotency_scope() {
            IdempotencyScope::Durable => self.begin_durable_idempotent(request, key, &request_hash),
            IdempotencyScope::ProcessLocal => {
                self.begin_process_idempotent(request, key, request_hash)
            }
            IdempotencyScope::None => IdempotencyAction::Respond(failure(
                request,
                crate::protocol::error_code::IDEMPOTENCY_ERROR,
                "mutating operation has no idempotency scope",
            )),
        }
    }

    fn begin_durable_idempotent(
        &self,
        request: &Request,
        key: &str,
        request_hash: &str,
    ) -> IdempotencyAction {
        let reservation = match self.store.reserve_idempotency_request(
            key,
            request.operation.name(),
            request_hash,
        ) {
            Ok(reservation) => reservation,
            Err(error) => {
                return IdempotencyAction::Respond(failure(
                    request,
                    crate::protocol::error_code::IDEMPOTENCY_ERROR,
                    &format!("could not reserve idempotent request: {error}"),
                ));
            }
        };
        match reservation {
            IdempotencyReservation::New => IdempotencyAction::Execute,
            IdempotencyReservation::Completed {
                operation,
                request_hash: stored_hash,
                response_json,
            } if operation == request.operation.name() && stored_hash == request_hash => {
                match serde_json::from_str::<Response>(&response_json) {
                    Ok(mut response) => {
                        response.request_id.clone_from(&request.request_id);
                        IdempotencyAction::Respond(response)
                    }
                    Err(error) => IdempotencyAction::Respond(failure(
                        request,
                        crate::protocol::error_code::IDEMPOTENCY_ERROR,
                        &format!("cached idempotent response is invalid: {error}"),
                    )),
                }
            }
            IdempotencyReservation::Pending {
                operation,
                request_hash: stored_hash,
            } if operation == request.operation.name() && stored_hash == request_hash => {
                IdempotencyAction::Respond(failure(
                    request,
                    crate::protocol::error_code::OUTCOME_UNKNOWN,
                    "a previous attempt may have applied this mutation; reconcile its state before issuing a new request",
                ))
            }
            IdempotencyReservation::Completed { operation, .. }
            | IdempotencyReservation::Pending { operation, .. } => {
                IdempotencyAction::Respond(failure(
                    request,
                    crate::protocol::error_code::IDEMPOTENCY_CONFLICT,
                    &format!(
                        "idempotency key was already used for a different payload ({operation})"
                    ),
                ))
            }
        }
    }

    fn begin_process_idempotent(
        &mut self,
        request: &Request,
        key: &str,
        request_hash: String,
    ) -> IdempotencyAction {
        if let Some(existing) = self.process_idempotency_requests.get(key) {
            if existing.operation == request.operation.name()
                && existing.request_hash == request_hash
            {
                return IdempotencyAction::Execute;
            }
            return IdempotencyAction::Respond(failure(
                request,
                crate::protocol::error_code::IDEMPOTENCY_CONFLICT,
                &format!(
                    "process-local idempotency key was already used for a different payload ({})",
                    existing.operation
                ),
            ));
        }
        self.process_idempotency_requests.insert(
            key.to_owned(),
            request.operation.name().to_owned(),
            request_hash,
        );
        IdempotencyAction::Execute
    }

    pub(super) fn complete_idempotent(
        &self,
        operation: &Operation,
        key: &str,
        encoded_response: &str,
    ) -> Result<()> {
        match operation.idempotency_scope() {
            IdempotencyScope::Durable => self
                .store
                .complete_idempotency_request(key, encoded_response),
            IdempotencyScope::ProcessLocal => Ok(()),
            IdempotencyScope::None => bail!("mutating operation has no idempotency scope"),
        }
    }
}

fn operation_hash(operation: &Operation) -> Result<String> {
    let payload = serde_json::to_vec(operation)?;
    Ok(blake3::hash(&payload).to_hex().to_string())
}

#[cfg(test)]
mod tests {
    use super::{PROCESS_IDEMPOTENCY_CAPACITY, ProcessIdempotencyRequests};

    #[test]
    fn process_idempotency_registry_evicts_the_oldest_key() {
        let mut requests = ProcessIdempotencyRequests::default();
        for index in 0..=PROCESS_IDEMPOTENCY_CAPACITY {
            requests.insert(
                format!("key-{index}"),
                "mount_workspace".into(),
                format!("hash-{index}"),
            );
        }

        assert_eq!(requests.entries.len(), PROCESS_IDEMPOTENCY_CAPACITY);
        assert!(requests.get("key-0").is_none());
        assert!(requests.get("key-1").is_some());
        assert!(
            requests
                .get(&format!("key-{PROCESS_IDEMPOTENCY_CAPACITY}"))
                .is_some()
        );
    }
}
