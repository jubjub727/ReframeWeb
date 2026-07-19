use prost::Message;
use reframe_store_protocol::wire::{
    ComponentInvocationRequest, FailureCode, InvocationEvent, ReadResourceRequest,
    component_invocation_request, invocation_event,
};
use reframe_store_sdk::{DecodedInvocation, EventBuilder, EventError, pack};

#[derive(Clone, PartialEq, Message)]
struct Value {
    #[prost(uint32, tag = "1")]
    number: u32,
}

impl prost::Name for Value {
    const NAME: &'static str = "Value";
    const PACKAGE: &'static str = "test.sdk";
}

fn read_request() -> DecodedInvocation {
    let request = ComponentInvocationRequest {
        request_id: "18cbcc79-feb9-4ca9-9ae6-b03d3b1d6369".to_owned(),
        operation: Some(component_invocation_request::Operation::ReadResource(
            ReadResourceRequest {
                resource_id: "example.value".to_owned(),
                selector: Some(pack(&Value { number: 1 }).unwrap()),
            },
        )),
    };
    DecodedInvocation::decode(&request.encode_to_vec()).unwrap()
}

#[test]
fn produces_started_data_complete_in_order() {
    let request = read_request();
    let mut builder = EventBuilder::for_request(&request).unwrap();
    builder.data(&Value { number: 42 }).unwrap();
    let invocation = builder.complete().unwrap();

    let events = std::iter::from_fn(|| invocation.next().unwrap())
        .map(|bytes| InvocationEvent::decode(bytes.as_slice()).unwrap())
        .collect::<Vec<_>>();
    assert_eq!(events.len(), 3);
    assert!(matches!(
        events[0].event,
        Some(invocation_event::Event::Started(_))
    ));
    assert!(matches!(
        events[1].event,
        Some(invocation_event::Event::Data(_))
    ));
    assert!(matches!(
        events[2].event,
        Some(invocation_event::Event::Complete(_))
    ));
    assert_eq!(events[2].sequence_number, 2);
}

#[test]
fn unary_stream_requires_exactly_one_value() {
    let request = read_request();
    assert!(matches!(
        EventBuilder::for_request(&request).unwrap().complete(),
        Err(EventError::UnaryCardinality)
    ));

    let mut builder = EventBuilder::for_request(&request).unwrap();
    builder.data(&Value { number: 1 }).unwrap();
    assert!(matches!(
        builder.data(&Value { number: 2 }),
        Err(EventError::UnaryCardinality)
    ));
}

#[test]
fn failure_is_a_terminal_stream_even_without_data() {
    let invocation = EventBuilder::for_request(&read_request())
        .unwrap()
        .failure(FailureCode::Unavailable, "offline", true, None)
        .unwrap();
    assert_eq!(invocation.remaining().unwrap(), 2);
}
