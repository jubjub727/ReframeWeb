use std::cell::RefCell;

use prost_types::Any;
use reframe_store_protocol::wire::FailureCode;

use crate::{
    EventError, GuestError, InvocationMode, StoreMessage, event_encoder::EventEncoder,
    events::mode_for, pack, request::DecodedInvocation,
};

/// One high-level event produced by a pull-driven invocation state machine.
#[derive(Debug)]
#[non_exhaustive]
pub enum InvocationStep {
    Data(Any),
    Progress {
        completed: u64,
        total: Option<u64>,
        unit: String,
        message: String,
    },
    Complete,
    Failure {
        code: FailureCode,
        message: String,
        retryable: bool,
        details: Option<Any>,
    },
}

impl InvocationStep {
    pub fn data<T: StoreMessage>(value: &T) -> Result<Self, GuestError> {
        pack(value)
            .map(Self::Data)
            .map_err(EventError::from)
            .map_err(GuestError::from)
    }

    #[must_use]
    pub fn progress(
        completed: u64,
        total: Option<u64>,
        unit: impl Into<String>,
        message: impl Into<String>,
    ) -> Self {
        Self::Progress {
            completed,
            total,
            unit: unit.into(),
            message: message.into(),
        }
    }

    #[must_use]
    pub fn failure(
        code: FailureCode,
        message: impl Into<String>,
        retryable: bool,
        details: Option<Any>,
    ) -> Self {
        Self::Failure {
            code,
            message: message.into(),
            retryable,
            details,
        }
    }

    const fn is_terminal(&self) -> bool {
        matches!(self, Self::Complete | Self::Failure { .. })
    }
}

/// Application state advanced exactly once for each post-`Started` WIT pull.
pub trait InvocationSource {
    fn next(&mut self) -> Result<InvocationStep, GuestError>;
}

impl<F> InvocationSource for F
where
    F: FnMut() -> Result<InvocationStep, GuestError>,
{
    fn next(&mut self) -> Result<InvocationStep, GuestError> {
        self()
    }
}

/// An invocation that retains application state and encodes one event per pull.
pub struct PullInvocation {
    state: RefCell<PullState>,
}

impl PullInvocation {
    pub fn for_request(
        request: &DecodedInvocation,
        source: impl InvocationSource + 'static,
    ) -> Result<Self, EventError> {
        Self::new(request.request_id().to_owned(), mode_for(request), source)
    }

    pub fn new(
        request_id: String,
        mode: InvocationMode,
        source: impl InvocationSource + 'static,
    ) -> Result<Self, EventError> {
        Ok(Self {
            state: RefCell::new(PullState {
                encoder: EventEncoder::new(request_id, mode)?,
                source: Box::new(source),
                started: false,
                terminal: false,
            }),
        })
    }

    /// Advances the source at most once and returns one encoded event.
    pub fn next(&self) -> Result<Option<Vec<u8>>, GuestError> {
        let mut state = self
            .state
            .try_borrow_mut()
            .map_err(|_| EventError::ReentrantPoll)?;
        if state.terminal {
            return Ok(None);
        }
        if !state.started {
            let started = state.encoder.started()?;
            state.started = true;
            return Ok(Some(started));
        }

        let step = state.source.next()?;
        let terminal = step.is_terminal();
        let encoded = state.encode(step)?;
        state.terminal = terminal;
        Ok(Some(encoded))
    }
}

impl std::fmt::Debug for PullInvocation {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("PullInvocation")
            .finish_non_exhaustive()
    }
}

struct PullState {
    encoder: EventEncoder,
    source: Box<dyn InvocationSource>,
    started: bool,
    terminal: bool,
}

impl PullState {
    fn encode(&mut self, step: InvocationStep) -> Result<Vec<u8>, EventError> {
        match step {
            InvocationStep::Data(value) => self.encoder.data(value),
            InvocationStep::Progress {
                completed,
                total,
                unit,
                message,
            } => self.encoder.progress(completed, total, unit, message),
            InvocationStep::Complete => self.encoder.complete(),
            InvocationStep::Failure {
                code,
                message,
                retryable,
                details,
            } => self.encoder.failure(code, message, retryable, details),
        }
    }
}
