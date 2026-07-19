use prost::Message;
use prost_types::Any;
use reframe_store_protocol::wire::{
    CallFunctionRequest, ComponentInvocationRequest, ReadResourceRequest, SubscribeResourceRequest,
    component_invocation_request,
};

use crate::{RequestError, StoreMessage, unpack};

/// A decoded and structurally validated request from the host.
#[derive(Debug, Clone)]
pub struct DecodedInvocation {
    request_id: String,
    operation: InvocationOperation,
}

impl DecodedInvocation {
    pub fn decode(bytes: &[u8]) -> Result<Self, RequestError> {
        let request = ComponentInvocationRequest::decode(bytes).map_err(RequestError::Decode)?;
        request.validate().map_err(RequestError::Invalid)?;
        let operation = request
            .operation
            .ok_or(RequestError::MissingOperation)?
            .into();
        Ok(Self {
            request_id: request.request_id,
            operation,
        })
    }

    #[must_use]
    pub fn request_id(&self) -> &str {
        &self.request_id
    }

    #[must_use]
    pub const fn operation(&self) -> &InvocationOperation {
        &self.operation
    }

    /// Decodes the operation's selector or input as a concrete Store message.
    pub fn input<T: StoreMessage>(&self) -> Result<T, RequestError> {
        unpack(self.operation.value()).map_err(RequestError::Input)
    }
}

/// The semantic operation selected by the fixed component request.
#[derive(Debug, Clone)]
pub enum InvocationOperation {
    ReadResource(ReadResourceRequest),
    SubscribeResource(SubscribeResourceRequest),
    CallFunction(CallFunctionRequest),
}

impl InvocationOperation {
    #[must_use]
    pub fn capability_id(&self) -> &str {
        match self {
            Self::ReadResource(request) => &request.resource_id,
            Self::SubscribeResource(request) => &request.resource_id,
            Self::CallFunction(request) => &request.function_id,
        }
    }

    #[must_use]
    pub const fn is_subscription(&self) -> bool {
        matches!(self, Self::SubscribeResource(_))
    }

    #[must_use]
    pub fn idempotency_key(&self) -> Option<&str> {
        match self {
            Self::CallFunction(request) if !request.idempotency_key.is_empty() => {
                Some(&request.idempotency_key)
            }
            _ => None,
        }
    }

    #[must_use]
    pub fn value(&self) -> &Any {
        match self {
            Self::ReadResource(request) => request.selector.as_ref(),
            Self::SubscribeResource(request) => request.selector.as_ref(),
            Self::CallFunction(request) => request.input.as_ref(),
        }
        .expect("validated invocation operations always contain an Any value")
    }
}

impl From<component_invocation_request::Operation> for InvocationOperation {
    fn from(operation: component_invocation_request::Operation) -> Self {
        match operation {
            component_invocation_request::Operation::ReadResource(request) => {
                Self::ReadResource(request)
            }
            component_invocation_request::Operation::SubscribeResource(request) => {
                Self::SubscribeResource(request)
            }
            component_invocation_request::Operation::CallFunction(request) => {
                Self::CallFunction(request)
            }
        }
    }
}
