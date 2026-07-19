use reframe_store_protocol::wire::{InvocationEvent, invocation_event};
use thiserror::Error;

/// Cardinality rules for one component invocation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InvocationMode {
    Unary,
    Subscription,
}

/// Ordered invocation-event validator.
#[derive(Debug, Clone)]
pub struct EventSequence {
    data_events: u64,
    mode: InvocationMode,
    next_sequence: u64,
    request_id: String,
    state: State,
}

impl EventSequence {
    #[must_use]
    pub fn new(request_id: String, mode: InvocationMode) -> Self {
        Self {
            data_events: 0,
            mode,
            next_sequence: 0,
            request_id,
            state: State::AwaitingStart,
        }
    }

    pub fn accept(&mut self, event: &InvocationEvent) -> Result<(), EventSequenceError> {
        event
            .validate()
            .map_err(|error| EventSequenceError::Malformed(error.to_string()))?;
        if event.request_id != self.request_id {
            return Err(EventSequenceError::WrongRequestId);
        }
        if event.sequence_number != self.next_sequence {
            return Err(EventSequenceError::WrongSequence {
                expected: self.next_sequence,
                actual: event.sequence_number,
            });
        }
        let kind = event
            .event
            .as_ref()
            .ok_or_else(|| EventSequenceError::Malformed("event kind is missing".to_owned()))?;

        match (self.state, kind) {
            (State::AwaitingStart, invocation_event::Event::Started(_)) => {
                self.state = State::Active;
            }
            (State::AwaitingStart, _) => return Err(EventSequenceError::StartedMustBeFirst),
            (State::Active, invocation_event::Event::Started(_)) => {
                return Err(EventSequenceError::DuplicateStarted);
            }
            (State::Active, invocation_event::Event::Data(_)) => {
                self.data_events += 1;
                if self.mode == InvocationMode::Unary && self.data_events > 1 {
                    return Err(EventSequenceError::TooManyUnaryDataEvents);
                }
            }
            (State::Active, invocation_event::Event::Progress(_)) => {}
            (State::Active, invocation_event::Event::Complete(_)) => {
                if self.mode == InvocationMode::Unary && self.data_events != 1 {
                    return Err(EventSequenceError::UnaryDataEventRequired);
                }
                self.state = State::Terminal;
            }
            (State::Active, invocation_event::Event::Failure(_)) => {
                self.state = State::Terminal;
            }
            (State::Terminal, _) => return Err(EventSequenceError::EventAfterTerminal),
        }
        self.next_sequence = self
            .next_sequence
            .checked_add(1)
            .ok_or(EventSequenceError::SequenceOverflow)?;
        Ok(())
    }

    pub fn finish(&self) -> Result<(), EventSequenceError> {
        if self.state == State::Terminal {
            Ok(())
        } else {
            Err(EventSequenceError::PrematureEnd)
        }
    }

    #[must_use]
    pub const fn is_terminal(&self) -> bool {
        matches!(self.state, State::Terminal)
    }

    #[must_use]
    pub const fn next_sequence(&self) -> u64 {
        self.next_sequence
    }

    #[must_use]
    pub fn request_id(&self) -> &str {
        &self.request_id
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum State {
    AwaitingStart,
    Active,
    Terminal,
}

#[derive(Debug, Clone, PartialEq, Eq, Error)]
#[non_exhaustive]
pub enum EventSequenceError {
    #[error("malformed invocation event: {0}")]
    Malformed(String),
    #[error("invocation event belongs to another request")]
    WrongRequestId,
    #[error("invocation event sequence is {actual}, expected {expected}")]
    WrongSequence { expected: u64, actual: u64 },
    #[error("Started must be the first invocation event")]
    StartedMustBeFirst,
    #[error("Started may be emitted only once")]
    DuplicateStarted,
    #[error("a unary invocation emitted more than one Data event")]
    TooManyUnaryDataEvents,
    #[error("a unary invocation must emit one Data event before Complete")]
    UnaryDataEventRequired,
    #[error("an event was emitted after the terminal event")]
    EventAfterTerminal,
    #[error("the component event stream ended before Complete or Failure")]
    PrematureEnd,
    #[error("invocation event sequence overflowed")]
    SequenceOverflow,
}

#[cfg(test)]
mod tests {
    use reframe_store_protocol::wire::{
        InvocationComplete, InvocationData, InvocationStarted, invocation_event,
    };

    use super::*;

    fn event(request_id: &str, sequence: u64, event: invocation_event::Event) -> InvocationEvent {
        InvocationEvent {
            request_id: request_id.to_owned(),
            sequence_number: sequence,
            event: Some(event),
        }
    }

    #[test]
    fn accepts_the_unary_contract() {
        let request_id = uuid::Uuid::new_v4().to_string();
        let mut sequence = EventSequence::new(request_id.clone(), InvocationMode::Unary);
        sequence
            .accept(&event(
                &request_id,
                0,
                invocation_event::Event::Started(InvocationStarted {}),
            ))
            .unwrap();
        sequence
            .accept(&event(
                &request_id,
                1,
                invocation_event::Event::Data(InvocationData {
                    value: Some(prost_types::Any {
                        type_url: "type.googleapis.com/test.Value".to_owned(),
                        value: Vec::new(),
                    }),
                }),
            ))
            .unwrap();
        sequence
            .accept(&event(
                &request_id,
                2,
                invocation_event::Event::Complete(InvocationComplete {}),
            ))
            .unwrap();
        assert!(sequence.finish().is_ok());
    }

    #[test]
    fn rejects_premature_and_duplicate_events() {
        let request_id = uuid::Uuid::new_v4().to_string();
        let mut sequence = EventSequence::new(request_id.clone(), InvocationMode::Subscription);
        let data = event(
            &request_id,
            0,
            invocation_event::Event::Data(InvocationData {
                value: Some(prost_types::Any {
                    type_url: "type.googleapis.com/test.Value".to_owned(),
                    value: Vec::new(),
                }),
            }),
        );
        assert_eq!(
            sequence.accept(&data),
            Err(EventSequenceError::StartedMustBeFirst)
        );
        assert_eq!(sequence.finish(), Err(EventSequenceError::PrematureEnd));
    }
}
