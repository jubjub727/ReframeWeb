use std::{cell::RefCell, collections::VecDeque};

use prost_types::Any;
use reframe_store_protocol::wire::FailureCode;

use crate::{
    EventError, StoreMessage, event_encoder::EventEncoder, pack, request::DecodedInvocation,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InvocationMode {
    Unary,
    Subscription,
}

/// Constructs a complete, ordered event stream before it crosses WIT.
///
/// `Started` is emitted automatically. A [`BufferedInvocation`] can only be
/// obtained by adding either `Complete` or `Failure`, so an accidental
/// premature end cannot be exported.
pub struct EventBuilder {
    encoder: EventEncoder,
    events: VecDeque<Vec<u8>>,
}

impl EventBuilder {
    pub fn for_request(request: &DecodedInvocation) -> Result<Self, EventError> {
        Self::new(request.request_id().to_owned(), mode_for(request))
    }

    pub fn new(request_id: String, mode: InvocationMode) -> Result<Self, EventError> {
        let mut encoder = EventEncoder::new(request_id, mode)?;
        let events = VecDeque::from([encoder.started()?]);
        Ok(Self { encoder, events })
    }

    pub fn data<T: StoreMessage>(&mut self, value: &T) -> Result<(), EventError> {
        self.data_any(pack(value)?)
    }

    pub fn data_any(&mut self, value: Any) -> Result<(), EventError> {
        self.events.push_back(self.encoder.data(value)?);
        Ok(())
    }

    pub fn progress(
        &mut self,
        completed: u64,
        total: Option<u64>,
        unit: impl Into<String>,
        message: impl Into<String>,
    ) -> Result<(), EventError> {
        self.events.push_back(self.encoder.progress(
            completed,
            total,
            unit.into(),
            message.into(),
        )?);
        Ok(())
    }

    pub fn complete(mut self) -> Result<BufferedInvocation, EventError> {
        self.events.push_back(self.encoder.complete()?);
        Ok(BufferedInvocation::new(self.events))
    }

    pub fn failure(
        mut self,
        code: FailureCode,
        message: impl Into<String>,
        retryable: bool,
        details: Option<Any>,
    ) -> Result<BufferedInvocation, EventError> {
        self.events.push_back(
            self.encoder
                .failure(code, message.into(), retryable, details)?,
        );
        Ok(BufferedInvocation::new(self.events))
    }
}

/// A terminal event stream ready to implement WIT `invocation.next`.
pub struct BufferedInvocation {
    events: RefCell<VecDeque<Vec<u8>>>,
}

impl BufferedInvocation {
    fn new(events: VecDeque<Vec<u8>>) -> Self {
        Self {
            events: RefCell::new(events),
        }
    }

    /// Returns one encoded `InvocationEvent`, then `None` after the terminal event.
    pub fn next(&self) -> Result<Option<Vec<u8>>, EventError> {
        self.events
            .try_borrow_mut()
            .map(|mut events| events.pop_front())
            .map_err(|_| EventError::ReentrantPoll)
    }

    pub fn remaining(&self) -> Result<usize, EventError> {
        self.events
            .try_borrow()
            .map(|events| events.len())
            .map_err(|_| EventError::ReentrantPoll)
    }
}

impl std::fmt::Debug for EventBuilder {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("EventBuilder")
            .field("buffered_events", &self.events.len())
            .finish_non_exhaustive()
    }
}

impl std::fmt::Debug for BufferedInvocation {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("BufferedInvocation")
            .finish_non_exhaustive()
    }
}

pub(crate) const fn mode_for(request: &DecodedInvocation) -> InvocationMode {
    if request.operation().is_subscription() {
        InvocationMode::Subscription
    } else {
        InvocationMode::Unary
    }
}
