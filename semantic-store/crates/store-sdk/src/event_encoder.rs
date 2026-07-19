use prost::Message;
use prost_types::Any;
use reframe_store_protocol::{
    validate_uuid,
    wire::{
        FailureCode, InvocationComplete, InvocationData, InvocationEvent, InvocationFailure,
        InvocationProgress, InvocationStarted, invocation_event,
    },
};

use crate::{EventError, InvocationMode, any::any_type_name, error::validate_failure_code};

pub(crate) struct EventEncoder {
    data_events: u64,
    mode: InvocationMode,
    next_sequence: u64,
    request_id: String,
}

impl EventEncoder {
    pub(crate) fn new(request_id: String, mode: InvocationMode) -> Result<Self, EventError> {
        validate_uuid("invocation_event.request_id", &request_id)
            .map_err(EventError::InvalidRequestId)?;
        Ok(Self {
            data_events: 0,
            mode,
            next_sequence: 0,
            request_id,
        })
    }

    pub(crate) fn started(&mut self) -> Result<Vec<u8>, EventError> {
        self.encode(invocation_event::Event::Started(InvocationStarted {}))
    }

    pub(crate) fn data(&mut self, value: Any) -> Result<Vec<u8>, EventError> {
        any_type_name(&value)?;
        if self.mode == InvocationMode::Unary && self.data_events == 1 {
            return Err(EventError::UnaryCardinality);
        }
        let encoded = self.encode(invocation_event::Event::Data(InvocationData {
            value: Some(value),
        }))?;
        self.data_events += 1;
        Ok(encoded)
    }

    pub(crate) fn progress(
        &mut self,
        completed: u64,
        total: Option<u64>,
        unit: String,
        message: String,
    ) -> Result<Vec<u8>, EventError> {
        if let Some(total) = total
            && total < completed
        {
            return Err(EventError::InvalidProgress { completed, total });
        }
        self.encode(invocation_event::Event::Progress(InvocationProgress {
            completed,
            total,
            unit,
            message,
        }))
    }

    pub(crate) fn complete(&mut self) -> Result<Vec<u8>, EventError> {
        if self.mode == InvocationMode::Unary && self.data_events != 1 {
            return Err(EventError::UnaryCardinality);
        }
        self.encode(invocation_event::Event::Complete(InvocationComplete {}))
    }

    pub(crate) fn failure(
        &mut self,
        code: FailureCode,
        message: String,
        retryable: bool,
        details: Option<Any>,
    ) -> Result<Vec<u8>, EventError> {
        validate_failure_code(code)?;
        if let Some(details) = &details {
            any_type_name(details)?;
        }
        self.encode(invocation_event::Event::Failure(InvocationFailure {
            code: code as i32,
            message,
            retryable,
            details,
        }))
    }

    fn encode(&mut self, event: invocation_event::Event) -> Result<Vec<u8>, EventError> {
        let next_sequence = self
            .next_sequence
            .checked_add(1)
            .ok_or(EventError::SequenceOverflow)?;
        let envelope = InvocationEvent {
            request_id: self.request_id.clone(),
            sequence_number: self.next_sequence,
            event: Some(event),
        };
        let mut encoded = Vec::with_capacity(envelope.encoded_len());
        envelope.encode(&mut encoded).map_err(EventError::Encode)?;
        self.next_sequence = next_sequence;
        Ok(encoded)
    }
}
