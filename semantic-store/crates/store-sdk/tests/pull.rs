use std::{cell::Cell, rc::Rc};

use prost::Message;
use reframe_store_protocol::wire::{
    ComponentInvocationRequest, InvocationEvent, SubscribeResourceRequest,
    component_invocation_request, invocation_event,
};
use reframe_store_sdk::{
    DecodedInvocation, EventError, GuestError, Invocation, InvocationMode, InvocationSource,
    InvocationStep, PullInvocation, pack,
};

#[derive(Clone, PartialEq, Message)]
struct Value {
    #[prost(uint32, tag = "1")]
    number: u32,
}

impl prost::Name for Value {
    const NAME: &'static str = "PullValue";
    const PACKAGE: &'static str = "test.sdk";
}

#[test]
fn advances_retained_source_once_per_post_started_pull() {
    let polls = Rc::new(Cell::new(0));
    let source = CountingSource {
        polls: Rc::clone(&polls),
    };
    let invocation = Invocation::from(PullInvocation::for_request(&request(), source).unwrap());

    let started = next_event(&invocation);
    assert_eq!(polls.get(), 0, "Started must not advance application state");
    assert!(matches!(
        started.event,
        Some(invocation_event::Event::Started(_))
    ));

    let data = next_event(&invocation);
    assert_eq!(polls.get(), 1);
    assert!(matches!(data.event, Some(invocation_event::Event::Data(_))));

    let progress = next_event(&invocation);
    assert_eq!(polls.get(), 2);
    assert!(matches!(
        progress.event,
        Some(invocation_event::Event::Progress(_))
    ));

    let complete = next_event(&invocation);
    assert_eq!(polls.get(), 3);
    assert!(matches!(
        complete.event,
        Some(invocation_event::Event::Complete(_))
    ));
    assert_eq!(invocation.next().unwrap(), None);
    assert_eq!(polls.get(), 3, "terminal sources must not be polled again");
}

#[test]
fn pull_stream_enforces_unary_cardinality_and_progress_bounds() {
    let unary = PullInvocation::new(
        "575322d5-63e1-45a9-ab77-1d688f5e9368".to_owned(),
        InvocationMode::Unary,
        || Ok(InvocationStep::Complete),
    )
    .unwrap();
    assert!(unary.next().unwrap().is_some());
    assert!(matches!(
        unary.next(),
        Err(GuestError::InvalidEvents(EventError::UnaryCardinality))
    ));

    let progress = PullInvocation::new(
        "80e4cb19-6e24-4d54-b619-f96cbd051a17".to_owned(),
        InvocationMode::Subscription,
        || Ok(InvocationStep::progress(2, Some(1), "items", "invalid")),
    )
    .unwrap();
    assert!(progress.next().unwrap().is_some());
    assert!(matches!(
        progress.next(),
        Err(GuestError::InvalidEvents(EventError::InvalidProgress {
            completed: 2,
            total: 1
        }))
    ));
}

struct CountingSource {
    polls: Rc<Cell<u32>>,
}

impl InvocationSource for CountingSource {
    fn next(&mut self) -> Result<InvocationStep, reframe_store_sdk::GuestError> {
        let poll = self.polls.get();
        self.polls.set(poll + 1);
        match poll {
            0 => InvocationStep::data(&Value { number: 7 }),
            1 => Ok(InvocationStep::progress(1, Some(1), "value", "ready")),
            2 => Ok(InvocationStep::Complete),
            _ => panic!("source polled after terminal event"),
        }
    }
}

fn request() -> DecodedInvocation {
    DecodedInvocation::decode(
        &ComponentInvocationRequest {
            request_id: "679888ca-6080-4c20-9f6e-f059a9dece26".to_owned(),
            operation: Some(component_invocation_request::Operation::SubscribeResource(
                SubscribeResourceRequest {
                    resource_id: "example.values".to_owned(),
                    selector: Some(pack(&Value { number: 1 }).unwrap()),
                },
            )),
        }
        .encode_to_vec(),
    )
    .unwrap()
}

fn next_event(invocation: &Invocation) -> InvocationEvent {
    let bytes = invocation.next().unwrap().expect("next event");
    InvocationEvent::decode(bytes.as_slice()).unwrap()
}
