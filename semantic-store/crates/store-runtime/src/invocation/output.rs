use std::{
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::Duration,
};

use reframe_store_protocol::wire::{
    Envelope, FailureCode, InvocationEvent, InvocationFailure, InvocationStarted, ProtocolVersion,
    envelope, invocation_event,
};
use thiserror::Error;

use crate::{
    DispatchError, EventSequence, EventSequenceError, InvocationMode, ResponseSink,
    sink::send_bounded,
};

pub(crate) struct InvocationOutput {
    closed: bool,
    finished: Arc<AtomicBool>,
    protocol: ProtocolVersion,
    sequence: EventSequence,
    session_id: String,
    sink: Arc<dyn ResponseSink>,
    timeout: Duration,
}

impl InvocationOutput {
    pub(crate) fn new(
        request_id: String,
        session_id: String,
        protocol: ProtocolVersion,
        mode: InvocationMode,
        sink: Arc<dyn ResponseSink>,
        timeout: Duration,
        finished: Arc<AtomicBool>,
    ) -> Self {
        Self {
            closed: false,
            finished,
            protocol,
            sequence: EventSequence::new(request_id, mode),
            session_id,
            sink,
            timeout,
        }
    }

    pub(crate) fn validate_candidate(
        &self,
        event: &InvocationEvent,
    ) -> Result<(), InvocationOutputError> {
        if self.closed {
            return Err(InvocationOutputError::Closed);
        }
        let mut candidate = self.sequence.clone();
        candidate.accept(event)?;
        Ok(())
    }

    pub(crate) async fn send_guest(
        &mut self,
        event: InvocationEvent,
    ) -> Result<(), InvocationOutputError> {
        self.send_event(event).await
    }

    pub(crate) async fn fail(
        &mut self,
        code: FailureCode,
        message: impl Into<String>,
    ) -> Result<(), InvocationOutputError> {
        if self.is_finished() {
            return Ok(());
        }
        if self.sequence.next_sequence() == 0 {
            self.send_event(InvocationEvent {
                request_id: self.request_id().to_owned(),
                sequence_number: 0,
                event: Some(invocation_event::Event::Started(InvocationStarted {})),
            })
            .await?;
        }
        self.send_event(InvocationEvent {
            request_id: self.request_id().to_owned(),
            sequence_number: self.sequence.next_sequence(),
            event: Some(invocation_event::Event::Failure(InvocationFailure {
                code: code as i32,
                message: message.into(),
                retryable: false,
                details: None,
            })),
        })
        .await
    }

    pub(crate) async fn cancel(&mut self) -> Result<(), InvocationOutputError> {
        let result = self
            .fail(FailureCode::Cancelled, "invocation was cancelled")
            .await;
        if result.is_err() {
            self.closed = true;
        }
        result
    }

    pub(crate) fn abandon(&mut self) {
        self.closed = true;
        self.finished.store(true, Ordering::Release);
    }

    pub(crate) fn is_finished(&self) -> bool {
        self.finished.load(Ordering::Acquire)
    }

    fn request_id(&self) -> &str {
        self.sequence.request_id()
    }

    async fn send_event(&mut self, event: InvocationEvent) -> Result<(), InvocationOutputError> {
        if self.closed {
            return Err(InvocationOutputError::Closed);
        }
        let mut candidate = self.sequence.clone();
        candidate.accept(&event)?;
        let envelope = Envelope {
            protocol_version: Some(self.protocol),
            session_id: self.session_id.clone(),
            request_id: event.request_id.clone(),
            sequence_number: event.sequence_number,
            message: Some(envelope::Message::InvocationEvent(event)),
        };
        if let Err(error) = send_bounded(&self.sink, envelope, self.timeout).await {
            self.closed = true;
            self.finished.store(true, Ordering::Release);
            return Err(error.into());
        }
        self.sequence = candidate;
        if self.sequence.is_terminal() {
            self.finished.store(true, Ordering::Release);
        }
        Ok(())
    }
}

#[derive(Debug, Error)]
pub(crate) enum InvocationOutputError {
    #[error(transparent)]
    Sequence(#[from] EventSequenceError),
    #[error(transparent)]
    Dispatch(#[from] DispatchError),
    #[error("invocation output is closed")]
    Closed,
}
