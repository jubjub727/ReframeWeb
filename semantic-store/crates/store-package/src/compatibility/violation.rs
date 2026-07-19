use thiserror::Error;

/// One deterministic protobuf compatibility violation.
#[derive(Debug, Clone, PartialEq, Eq, Error)]
#[non_exhaustive]
pub enum CompatibilityViolation {
    #[error("message {message:?} was removed")]
    MessageRemoved { message: String },
    #[error("message {message:?} changed map-entry status from {previous} to {candidate}")]
    MessageMapEntryChanged {
        message: String,
        previous: bool,
        candidate: bool,
    },
    #[error("enum {enumeration:?} was removed")]
    EnumRemoved { enumeration: String },
    #[error("service {service:?} was removed")]
    ServiceRemoved { service: String },
    #[error("method {service}.{method} was removed")]
    MethodRemoved { service: String, method: String },
    #[error("catalog capability {capability_id:?} was removed")]
    CapabilityRemoved { capability_id: String },
    #[error("catalog capability {capability_id:?} changed kind from {previous} to {candidate}")]
    CapabilityKindChanged {
        capability_id: String,
        previous: String,
        candidate: String,
    },
    #[error(
        "catalog capability {capability_id:?} changed {role} type from {previous:?} to {candidate:?}"
    )]
    CapabilityContractTypeChanged {
        capability_id: String,
        role: &'static str,
        previous: String,
        candidate: String,
    },
    #[error(
        "catalog capability {capability_id:?} changed method binding from {previous:?} to {candidate:?}"
    )]
    CapabilityMethodBindingChanged {
        capability_id: String,
        previous: String,
        candidate: String,
    },
    #[error("resource {capability_id:?} disabled subscription support")]
    ResourceSubscriptionsDisabled { capability_id: String },
    #[error(
        "function {capability_id:?} changed side-effect classification from {previous} to {candidate}"
    )]
    FunctionSideEffectChanged {
        capability_id: String,
        previous: i32,
        candidate: i32,
    },
    #[error("function {capability_id:?} changed idempotency from {previous} to {candidate}")]
    FunctionIdempotencyChanged {
        capability_id: String,
        previous: i32,
        candidate: i32,
    },
    #[error(
        "field {message}.{field} ({number}) was removed without reserving both its number and name (number_reserved={number_reserved}, name_reserved={name_reserved})"
    )]
    FieldRemovedWithoutReservation {
        message: String,
        field: String,
        number: i32,
        number_reserved: bool,
        name_reserved: bool,
    },
    #[error("message {message:?} no longer reserves field name {name:?}")]
    FieldNameReservationRemoved { message: String, name: String },
    #[error("message {message:?} no longer fully reserves field-number range [{start}, {end})")]
    FieldNumberReservationRemoved {
        message: String,
        start: i32,
        end: i32,
    },
    #[error("field {message}.{field} changed number from {previous} to {candidate}")]
    FieldNumberChanged {
        message: String,
        field: String,
        previous: i32,
        candidate: i32,
    },
    #[error("field {message} number {number} changed name from {previous:?} to {candidate:?}")]
    FieldNameChanged {
        message: String,
        number: i32,
        previous: String,
        candidate: String,
    },
    #[error("field {message}.{field} changed type from {previous} to {candidate}")]
    FieldTypeChanged {
        message: String,
        field: String,
        previous: String,
        candidate: String,
    },
    #[error("field {message}.{field} changed cardinality from {previous} to {candidate}")]
    FieldCardinalityChanged {
        message: String,
        field: String,
        previous: String,
        candidate: String,
    },
    #[error("field {message}.{field} changed oneof from {previous:?} to {candidate:?}")]
    FieldOneofChanged {
        message: String,
        field: String,
        previous: Option<String>,
        candidate: Option<String>,
    },
    #[error("field {message}.{field} changed explicit presence from {previous} to {candidate}")]
    FieldPresenceChanged {
        message: String,
        field: String,
        previous: bool,
        candidate: bool,
    },
    #[error(
        "field {message}.{field} changed its declared default from {previous:?} to {candidate:?}"
    )]
    FieldDefaultChanged {
        message: String,
        field: String,
        previous: Option<String>,
        candidate: Option<String>,
    },
    #[error("required field {message}.{field} ({number}) was added")]
    RequiredFieldAdded {
        message: String,
        field: String,
        number: i32,
    },
    #[error(
        "enum value {enumeration}.{value} ({number}) was removed without reserving both its number and name (number_reserved={number_reserved}, name_reserved={name_reserved})"
    )]
    EnumValueRemovedWithoutReservation {
        enumeration: String,
        value: String,
        number: i32,
        number_reserved: bool,
        name_reserved: bool,
    },
    #[error("enum {enumeration:?} no longer reserves value name {name:?}")]
    EnumNameReservationRemoved { enumeration: String, name: String },
    #[error("enum {enumeration:?} no longer fully reserves value-number range [{start}, {end}]")]
    EnumNumberReservationRemoved {
        enumeration: String,
        start: i32,
        end: i32,
    },
    #[error("enum value {enumeration}.{value} changed number from {previous} to {candidate}")]
    EnumValueNumberChanged {
        enumeration: String,
        value: String,
        previous: i32,
        candidate: i32,
    },
    #[error("RPC {service}.{method} changed input from {previous} to {candidate}")]
    RpcInputChanged {
        service: String,
        method: String,
        previous: String,
        candidate: String,
    },
    #[error("RPC {service}.{method} changed output from {previous} to {candidate}")]
    RpcOutputChanged {
        service: String,
        method: String,
        previous: String,
        candidate: String,
    },
    #[error("RPC {service}.{method} changed client_streaming from {previous} to {candidate}")]
    RpcClientStreamingChanged {
        service: String,
        method: String,
        previous: bool,
        candidate: bool,
    },
    #[error("RPC {service}.{method} changed server_streaming from {previous} to {candidate}")]
    RpcServerStreamingChanged {
        service: String,
        method: String,
        previous: bool,
        candidate: bool,
    },
}
