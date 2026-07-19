use crate::{
    MAX_CAPABILITY_ID_BYTES, MAX_IDEMPOTENCY_KEY_BYTES, validate_uuid,
    wire::{
        ComponentInvocationRequest, FailureCode, InvocationEvent, component_invocation_request,
        invocation_event,
    },
};

use super::{
    ValidationError,
    limits::{bounded_text, required_any, required_text},
};

impl ComponentInvocationRequest {
    pub fn validate(&self) -> Result<(), ValidationError> {
        validate_uuid("request_id", &self.request_id)?;
        let operation = self
            .operation
            .as_ref()
            .ok_or(ValidationError::MissingField { field: "operation" })?;
        match operation {
            component_invocation_request::Operation::ReadResource(request) => {
                validate_capability_and_value(
                    "read_resource.resource_id",
                    &request.resource_id,
                    "read_resource.selector",
                    request.selector.as_ref(),
                )?;
            }
            component_invocation_request::Operation::SubscribeResource(request) => {
                validate_capability_and_value(
                    "subscribe_resource.resource_id",
                    &request.resource_id,
                    "subscribe_resource.selector",
                    request.selector.as_ref(),
                )?;
            }
            component_invocation_request::Operation::CallFunction(request) => {
                validate_capability_and_value(
                    "call_function.function_id",
                    &request.function_id,
                    "call_function.input",
                    request.input.as_ref(),
                )?;
                bounded_text(
                    "call_function.idempotency_key",
                    &request.idempotency_key,
                    MAX_IDEMPOTENCY_KEY_BYTES,
                )?;
            }
        }
        Ok(())
    }
}

impl InvocationEvent {
    pub fn validate(&self) -> Result<(), ValidationError> {
        validate_uuid("invocation_event.request_id", &self.request_id)?;
        let event = self.event.as_ref().ok_or(ValidationError::MissingField {
            field: "invocation_event.event",
        })?;
        match event {
            invocation_event::Event::Data(data) => {
                required_any("invocation_event.data.value", data.value.as_ref())
            }
            invocation_event::Event::Progress(progress)
                if progress
                    .total
                    .is_some_and(|total| total < progress.completed) =>
            {
                Err(ValidationError::InvalidValue {
                    field: "invocation_event.progress.total",
                    reason: "total must not be less than completed",
                })
            }
            invocation_event::Event::Failure(failure) => {
                match FailureCode::try_from(failure.code).ok() {
                    Some(FailureCode::Unspecified) => Err(ValidationError::MissingField {
                        field: "invocation_event.failure.code",
                    }),
                    Some(_) => failure.details.as_ref().map_or(Ok(()), |details| {
                        required_any("invocation_event.failure.details", Some(details))
                    }),
                    None => Err(ValidationError::InvalidValue {
                        field: "invocation_event.failure.code",
                        reason: "failure code is unknown",
                    }),
                }
            }
            _ => Ok(()),
        }
    }
}

fn validate_capability_and_value(
    capability_field: &'static str,
    capability_id: &str,
    value_field: &'static str,
    value: Option<&prost_types::Any>,
) -> Result<(), ValidationError> {
    required_text(capability_field, capability_id, MAX_CAPABILITY_ID_BYTES)?;
    required_any(value_field, value)
}

#[cfg(test)]
mod tests {
    use prost_types::Any;

    use crate::wire::{InvocationFailure, InvocationProgress};

    use super::*;

    fn event(kind: invocation_event::Event) -> InvocationEvent {
        InvocationEvent {
            request_id: uuid::Uuid::new_v4().to_string(),
            event: Some(kind),
            ..InvocationEvent::default()
        }
    }

    #[test]
    fn rejects_unknown_failure_codes_and_malformed_details() {
        let unknown = event(invocation_event::Event::Failure(InvocationFailure {
            code: i32::MAX,
            ..InvocationFailure::default()
        }));
        assert!(matches!(
            unknown.validate(),
            Err(ValidationError::InvalidValue {
                field: "invocation_event.failure.code",
                ..
            })
        ));

        let malformed = event(invocation_event::Event::Failure(InvocationFailure {
            code: FailureCode::Internal as i32,
            details: Some(Any::default()),
            ..InvocationFailure::default()
        }));
        assert!(malformed.validate().is_err());
    }

    #[test]
    fn rejects_progress_past_its_declared_total() {
        let invalid = event(invocation_event::Event::Progress(InvocationProgress {
            completed: 2,
            total: Some(1),
            ..InvocationProgress::default()
        }));
        assert!(matches!(
            invalid.validate(),
            Err(ValidationError::InvalidValue {
                field: "invocation_event.progress.total",
                ..
            })
        ));
    }
}
