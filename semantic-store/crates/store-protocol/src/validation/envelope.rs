use crate::{
    CURRENT_PROTOCOL_VERSION, validate_store_id, validate_uuid,
    wire::{Envelope, envelope},
};

use super::{
    MAX_CAPABILITY_ID_BYTES, MAX_CURSOR_BYTES, MAX_FIELD_PATH_BYTES, MAX_FIELD_PATHS,
    MAX_IDEMPOTENCY_KEY_BYTES, MAX_INSPECTION_SECTIONS, MAX_QUERY_BYTES,
    MAX_REQUESTED_CAPABILITY_KINDS, MAX_TYPE_NAME_BYTES, ValidationError,
    limits::{bounded_count, bounded_text, required_any, required_text},
};

impl Envelope {
    pub fn validate(&self) -> Result<(), ValidationError> {
        let protocol = self
            .protocol_version
            .as_ref()
            .ok_or(ValidationError::MissingField {
                field: "protocol_version",
            })?;
        validate_uuid("request_id", &self.request_id)?;
        let message = self
            .message
            .as_ref()
            .ok_or(ValidationError::MissingField { field: "message" })?;
        if matches!(message, envelope::Message::OpenStoreRequest(_)) {
            protocol.validate()?;
            if protocol.major != CURRENT_PROTOCOL_VERSION.major {
                return Err(ValidationError::UnsupportedVersion {
                    found_major: protocol.major,
                    found_minor: protocol.minor,
                    supported_major: CURRENT_PROTOCOL_VERSION.major,
                    supported_minor: CURRENT_PROTOCOL_VERSION.minor,
                });
            }
        } else {
            protocol.ensure_supported()?;
        }

        if message.requires_session() || !self.session_id.is_empty() {
            validate_uuid("session_id", &self.session_id)?;
        }
        if message.is_request() && self.sequence_number != 0 {
            return Err(ValidationError::InvalidValue {
                field: "sequence_number",
                reason: "request envelopes must use sequence zero",
            });
        }

        match message {
            envelope::Message::OpenStoreRequest(request) => {
                validate_store_id(&request.store_id)?;
                request
                    .supported_protocol_version
                    .as_ref()
                    .ok_or(ValidationError::MissingField {
                        field: "open_store_request.supported_protocol_version",
                    })?
                    .validate()?;
                request
                    .required_interface
                    .as_ref()
                    .ok_or(ValidationError::MissingField {
                        field: "open_store_request.required_interface",
                    })?
                    .validate()?;
            }
            envelope::Message::OpenStoreResponse(response) => {
                validate_store_id(&response.store_id)?;
                response
                    .negotiated_protocol_version
                    .as_ref()
                    .ok_or(ValidationError::MissingField {
                        field: "open_store_response.negotiated_protocol_version",
                    })?
                    .ensure_supported()?;
                response
                    .semantic_interface_version
                    .as_ref()
                    .ok_or(ValidationError::MissingField {
                        field: "open_store_response.semantic_interface_version",
                    })?
                    .validate()?;
                validate_digest(
                    "open_store_response.catalog_revision",
                    &response.catalog_revision,
                )?;
            }
            envelope::Message::SearchCatalogRequest(request) => {
                bounded_text(
                    "search_catalog_request.query",
                    &request.query,
                    MAX_QUERY_BYTES,
                )?;
                bounded_count(
                    "search_catalog_request.kinds",
                    request.kinds.len(),
                    MAX_REQUESTED_CAPABILITY_KINDS,
                )?;
                bounded_text(
                    "search_catalog_request.topic_id",
                    &request.topic_id,
                    MAX_CAPABILITY_ID_BYTES,
                )?;
                bounded_text(
                    "search_catalog_request.cursor",
                    &request.cursor,
                    MAX_CURSOR_BYTES,
                )?;
            }
            envelope::Message::BrowseCatalogRequest(request) => {
                bounded_text(
                    "browse_catalog_request.parent_topic_id",
                    &request.parent_topic_id,
                    MAX_CAPABILITY_ID_BYTES,
                )?;
                bounded_count(
                    "browse_catalog_request.kinds",
                    request.kinds.len(),
                    MAX_REQUESTED_CAPABILITY_KINDS,
                )?;
                bounded_text(
                    "browse_catalog_request.cursor",
                    &request.cursor,
                    MAX_CURSOR_BYTES,
                )?;
            }
            envelope::Message::InspectCapabilityRequest(request) => {
                required_text(
                    "inspect_capability_request.capability_id",
                    &request.capability_id,
                    MAX_CAPABILITY_ID_BYTES,
                )?;
                bounded_count(
                    "inspect_capability_request.sections",
                    request.sections.len(),
                    MAX_INSPECTION_SECTIONS,
                )?;
            }
            envelope::Message::InspectTypeRequest(request) => {
                required_text(
                    "inspect_type_request.type_name",
                    &request.type_name,
                    MAX_TYPE_NAME_BYTES,
                )?;
                bounded_count(
                    "inspect_type_request.field_paths",
                    request.field_paths.len(),
                    MAX_FIELD_PATHS,
                )?;
                for field_path in &request.field_paths {
                    required_text(
                        "inspect_type_request.field_paths",
                        field_path,
                        MAX_FIELD_PATH_BYTES,
                    )?;
                }
            }
            envelope::Message::GetSchemaBundleRequest(request)
                if !request.known_artifact_hash.is_empty()
                    && request.known_artifact_hash.len() != 32 =>
            {
                return Err(ValidationError::InvalidValue {
                    field: "get_schema_bundle_request.known_artifact_hash",
                    reason: "known hash must be empty or contain exactly 32 bytes",
                });
            }
            envelope::Message::ReadResourceRequest(request) => {
                required_text(
                    "read_resource_request.resource_id",
                    &request.resource_id,
                    MAX_CAPABILITY_ID_BYTES,
                )?;
                required_any("read_resource_request.selector", request.selector.as_ref())?;
            }
            envelope::Message::SubscribeResourceRequest(request) => {
                required_text(
                    "subscribe_resource_request.resource_id",
                    &request.resource_id,
                    MAX_CAPABILITY_ID_BYTES,
                )?;
                required_any(
                    "subscribe_resource_request.selector",
                    request.selector.as_ref(),
                )?;
            }
            envelope::Message::CallFunctionRequest(request) => {
                required_text(
                    "call_function_request.function_id",
                    &request.function_id,
                    MAX_CAPABILITY_ID_BYTES,
                )?;
                required_any("call_function_request.input", request.input.as_ref())?;
                bounded_text(
                    "call_function_request.idempotency_key",
                    &request.idempotency_key,
                    MAX_IDEMPOTENCY_KEY_BYTES,
                )?;
            }
            envelope::Message::InvocationEvent(event) => {
                event.validate()?;
                if event.request_id != self.request_id {
                    return Err(ValidationError::MismatchedFields {
                        left: "request_id",
                        right: "invocation_event.request_id",
                    });
                }
                if event.sequence_number != self.sequence_number {
                    return Err(ValidationError::MismatchedFields {
                        left: "sequence_number",
                        right: "invocation_event.sequence_number",
                    });
                }
            }
            envelope::Message::CancelInvocationRequest(request) => validate_uuid(
                "cancel_invocation_request.target_request_id",
                &request.target_request_id,
            )?,
            envelope::Message::CancelInvocationResponse(response) => {
                validate_uuid(
                    "cancel_invocation_response.target_request_id",
                    &response.target_request_id,
                )?;
                if response.state == 0 {
                    return Err(ValidationError::MissingField {
                        field: "cancel_invocation_response.state",
                    });
                }
            }
            _ => {}
        }
        Ok(())
    }
}

impl envelope::Message {
    const fn is_request(&self) -> bool {
        matches!(
            self,
            Self::OpenStoreRequest(_)
                | Self::GetStoreCardRequest(_)
                | Self::SearchCatalogRequest(_)
                | Self::BrowseCatalogRequest(_)
                | Self::InspectCapabilityRequest(_)
                | Self::InspectTypeRequest(_)
                | Self::GetSchemaBundleRequest(_)
                | Self::ReadResourceRequest(_)
                | Self::SubscribeResourceRequest(_)
                | Self::CallFunctionRequest(_)
                | Self::CancelInvocationRequest(_)
                | Self::CloseStoreRequest(_)
        )
    }

    const fn requires_session(&self) -> bool {
        !matches!(self, Self::OpenStoreRequest(_) | Self::Error(_))
    }
}

fn validate_digest(field: &'static str, digest: &[u8]) -> Result<(), ValidationError> {
    if digest.len() != 32 {
        return Err(ValidationError::InvalidValue {
            field,
            reason: "SHA-256 digest must contain exactly 32 bytes",
        });
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use uuid::Uuid;

    use crate::{
        CURRENT_PROTOCOL_VERSION,
        wire::{Envelope, GetStoreCardRequest, InspectCapabilityRequest, envelope},
    };

    use super::*;

    #[test]
    fn request_requires_a_session_uuid() {
        let envelope = Envelope {
            protocol_version: Some(CURRENT_PROTOCOL_VERSION),
            request_id: Uuid::new_v4().to_string(),
            message: Some(envelope::Message::GetStoreCardRequest(
                GetStoreCardRequest {},
            )),
            ..Envelope::default()
        };
        assert!(matches!(
            envelope.validate(),
            Err(ValidationError::InvalidUuid {
                field: "session_id",
                ..
            })
        ));
    }

    #[test]
    fn open_allows_a_future_same_major_minor_for_negotiation() {
        let envelope = Envelope {
            protocol_version: Some(crate::wire::ProtocolVersion { major: 1, minor: 9 }),
            request_id: Uuid::new_v4().to_string(),
            message: Some(envelope::Message::OpenStoreRequest(
                crate::wire::OpenStoreRequest {
                    store_id: "dev.reframe.example".to_owned(),
                    supported_protocol_version: Some(crate::wire::ProtocolVersion {
                        major: 1,
                        minor: 9,
                    }),
                    required_interface: Some(crate::wire::InterfaceRequirement {
                        major: 1,
                        min_minor: 0,
                        max_minor: None,
                    }),
                },
            )),
            ..Envelope::default()
        };
        envelope.validate().unwrap();
    }

    #[test]
    fn oversized_identifiers_are_rejected_before_catalog_lookup() {
        let envelope = Envelope {
            protocol_version: Some(CURRENT_PROTOCOL_VERSION),
            session_id: Uuid::new_v4().to_string(),
            request_id: Uuid::new_v4().to_string(),
            message: Some(envelope::Message::InspectCapabilityRequest(
                InspectCapabilityRequest {
                    capability_id: "x".repeat(MAX_CAPABILITY_ID_BYTES + 1),
                    ..InspectCapabilityRequest::default()
                },
            )),
            ..Envelope::default()
        };
        assert!(matches!(
            envelope.validate(),
            Err(ValidationError::InvalidValue {
                field: "inspect_capability_request.capability_id",
                ..
            })
        ));
    }
}
