use prost_reflect::DynamicMessage;
use prost_types::Any;
use reframe_store_protocol::package::{CapabilityKind, catalog_entry};
use reframe_store_protocol::{ProtobufShapeBudget, UnknownFieldPolicy, validate_message_shape};

use crate::{CatalogError, CatalogService};

const VALUE_SHAPE_BUDGET: ProtobufShapeBudget = ProtobufShapeBudget::new(16_384, 64);

/// Runtime execution shape established only after input validation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InvocationMode {
    Unary,
    Subscription,
}

/// An unforgeable-by-construction lookup result for runtime dispatch and output
/// validation. Fields are private so contracts can only originate in a service.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InvocationContract {
    capability_id: String,
    kind: CapabilityKind,
    expected_output_type: String,
    mode: InvocationMode,
    catalog_revision: [u8; 32],
}

impl InvocationContract {
    #[must_use]
    pub fn capability_id(&self) -> &str {
        &self.capability_id
    }

    #[must_use]
    pub const fn kind(&self) -> CapabilityKind {
        self.kind
    }

    #[must_use]
    pub fn expected_output_type(&self) -> &str {
        &self.expected_output_type
    }

    #[must_use]
    pub const fn mode(&self) -> InvocationMode {
        self.mode
    }
}

impl CatalogService {
    /// Validates a resource selector and returns its dispatch/output contract.
    pub fn validate_read(
        &self,
        resource_id: &str,
        selector: &Any,
        subscribe: bool,
    ) -> Result<InvocationContract, CatalogError> {
        let entry = self.entry(resource_id)?;
        let Some(catalog_entry::Kind::Resource(resource)) = entry.kind.as_ref() else {
            return Err(CatalogError::CapabilityKindMismatch {
                capability_id: resource_id.to_owned(),
                expected: "resource",
            });
        };
        if subscribe && !resource.supports_subscriptions {
            return Err(CatalogError::SubscriptionsUnsupported {
                capability_id: resource_id.to_owned(),
            });
        }
        self.validate_any(selector, &resource.selector_type)?;
        Ok(InvocationContract {
            capability_id: resource_id.to_owned(),
            kind: CapabilityKind::Resource,
            expected_output_type: canonical_type_name(&resource.value_type).to_owned(),
            mode: if subscribe {
                InvocationMode::Subscription
            } else {
                InvocationMode::Unary
            },
            catalog_revision: self.revision,
        })
    }

    /// Validates a function input and returns its dispatch/output contract.
    pub fn validate_call(
        &self,
        function_id: &str,
        input: &Any,
    ) -> Result<InvocationContract, CatalogError> {
        let entry = self.entry(function_id)?;
        let Some(catalog_entry::Kind::Function(function)) = entry.kind.as_ref() else {
            return Err(CatalogError::CapabilityKindMismatch {
                capability_id: function_id.to_owned(),
                expected: "function",
            });
        };
        self.validate_any(input, &function.input_type)?;
        Ok(InvocationContract {
            capability_id: function_id.to_owned(),
            kind: CapabilityKind::Function,
            expected_output_type: canonical_type_name(&function.output_type).to_owned(),
            mode: InvocationMode::Unary,
            catalog_revision: self.revision,
        })
    }

    /// Validates a component-emitted value against the established contract.
    pub fn validate_output(
        &self,
        contract: &InvocationContract,
        output: &Any,
    ) -> Result<(), CatalogError> {
        if contract.catalog_revision != self.revision {
            return Err(CatalogError::ContractMismatch);
        }
        self.validate_any(output, &contract.expected_output_type)
    }

    fn validate_any(&self, value: &Any, expected_type: &str) -> Result<(), CatalogError> {
        let expected_type = canonical_type_name(expected_type);
        let actual_type = any_type_name(&value.type_url)?;
        if actual_type != expected_type {
            return Err(CatalogError::TypeMismatch {
                expected: expected_type.to_owned(),
                actual: actual_type.to_owned(),
            });
        }
        let descriptor = self
            .descriptor_pool
            .get_message_by_name(expected_type)
            .ok_or_else(|| CatalogError::TypeNotFound {
                type_name: expected_type.to_owned(),
            })?;
        validate_message_shape(
            &descriptor,
            &value.value,
            VALUE_SHAPE_BUDGET,
            UnknownFieldPolicy::Reject,
        )
        .map_err(|error| CatalogError::InvalidPayload {
            type_name: expected_type.to_owned(),
            reason: error.to_string(),
        })?;
        let message =
            DynamicMessage::decode(descriptor, value.value.as_slice()).map_err(|error| {
                CatalogError::InvalidPayload {
                    type_name: expected_type.to_owned(),
                    reason: error.to_string(),
                }
            })?;
        if message.unknown_fields().next().is_some() {
            return Err(CatalogError::InvalidPayload {
                type_name: expected_type.to_owned(),
                reason: "payload contains fields absent from the declared message".to_owned(),
            });
        }
        Ok(())
    }
}

fn any_type_name(type_url: &str) -> Result<&str, CatalogError> {
    let Some((prefix, type_name)) = type_url.rsplit_once('/') else {
        return Err(CatalogError::InvalidTypeUrl {
            type_url: type_url.to_owned(),
        });
    };
    if prefix.is_empty()
        || type_name.is_empty()
        || type_name.starts_with('.')
        || type_url.chars().any(char::is_whitespace)
    {
        return Err(CatalogError::InvalidTypeUrl {
            type_url: type_url.to_owned(),
        });
    }
    Ok(type_name)
}

fn canonical_type_name(type_name: &str) -> &str {
    type_name.trim().trim_start_matches('.')
}
