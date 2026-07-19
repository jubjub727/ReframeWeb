use reframe_store_catalog::CatalogError;
use reframe_store_protocol::wire::{ErrorCode, FieldViolation, ProtocolError};

#[derive(Debug)]
pub(crate) struct ProtocolFault {
    code: ErrorCode,
    message: String,
    retryable: bool,
    field_violations: Vec<FieldViolation>,
}

impl ProtocolFault {
    pub(crate) fn new(code: ErrorCode, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
            retryable: false,
            field_violations: Vec::new(),
        }
    }

    pub(crate) fn retryable(mut self) -> Self {
        self.retryable = true;
        self
    }

    pub(crate) fn field(
        mut self,
        field: impl Into<String>,
        description: impl Into<String>,
    ) -> Self {
        self.field_violations.push(FieldViolation {
            field: field.into(),
            description: description.into(),
        });
        self
    }

    pub(crate) fn into_message(self) -> ProtocolError {
        ProtocolError {
            code: self.code as i32,
            message: self.message,
            retryable: self.retryable,
            field_violations: self.field_violations,
            details: None,
        }
    }

    pub(crate) fn invalid_request(message: impl Into<String>) -> Self {
        Self::new(ErrorCode::InvalidRequest, message)
    }

    pub(crate) fn request_conflict(request_id: &str) -> Self {
        Self::new(
            ErrorCode::RequestConflict,
            format!("request {request_id:?} is already active in this session"),
        )
    }
}

impl From<CatalogError> for ProtocolFault {
    fn from(error: CatalogError) -> Self {
        let (code, message) = match &error {
            CatalogError::CapabilityNotFound { .. }
            | CatalogError::CapabilityKindMismatch { .. }
            | CatalogError::SubscriptionsUnsupported { .. } => (
                ErrorCode::CapabilityNotFound,
                "capability was not found or is incompatible",
            ),
            CatalogError::TopicNotFound { .. }
            | CatalogError::InvalidCapabilityKind { .. }
            | CatalogError::InvalidInspectionSection { .. }
            | CatalogError::InvalidFieldPath { .. }
            | CatalogError::InvalidTypeUrl { .. }
            | CatalogError::InvalidPayload { .. } => {
                (ErrorCode::InvalidRequest, "catalog request is invalid")
            }
            CatalogError::TypeNotFound { .. } => (ErrorCode::TypeNotFound, "type was not found"),
            CatalogError::InvalidCursor => (ErrorCode::InvalidCursor, "cursor is invalid"),
            CatalogError::StaleCursor => (
                ErrorCode::StaleCursor,
                "cursor belongs to a different catalog revision",
            ),
            CatalogError::InvalidBudget { .. } => {
                (ErrorCode::InvalidBudget, "byte budget is invalid")
            }
            CatalogError::BudgetExceeded { .. } => (
                ErrorCode::BudgetExceeded,
                "byte budget cannot hold the next complete item",
            ),
            CatalogError::TypeMismatch { .. } | CatalogError::ContractMismatch => (
                ErrorCode::TypeMismatch,
                "protobuf value does not match the capability contract",
            ),
            CatalogError::InvalidCatalog { .. } => {
                (ErrorCode::RuntimeError, "Store catalog is unavailable")
            }
            _ => (ErrorCode::RuntimeError, "Store catalog request failed"),
        };
        // Catalog errors often retain the rejected identifier or type URL for
        // diagnostics. Keep those values in host logs, never in client faults.
        tracing::debug!(%error, "catalog request rejected");
        Self::new(code, message)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn catalog_faults_do_not_echo_rejected_identifiers_or_type_urls() {
        let marker = "attacker-controlled-marker".repeat(5);
        for error in [
            CatalogError::CapabilityNotFound {
                capability_id: marker.clone(),
            },
            CatalogError::TypeNotFound {
                type_name: marker.clone(),
            },
            CatalogError::InvalidTypeUrl {
                type_url: marker.clone(),
            },
            CatalogError::InvalidPayload {
                type_name: marker.clone(),
                reason: marker.clone(),
            },
        ] {
            let fault = ProtocolFault::from(error).into_message();
            assert!(!fault.message.contains(&marker));
            assert!(fault.message.len() < 128);
        }
    }
}
