use std::{cell::Cell, rc::Rc};

use prost::Message;
use reframe_reference_store::{
    CounterSelector, HttpClient, HttpSnapshot, HttpTarget, LoopbackSelector, LoopbackSnapshot,
    NORMALIZE_LABEL_FUNCTION_ID, NormalizeLabelInput, NormalizeLabelOutput, ResourceError, invoke,
    invoke_with_http,
};
use reframe_store_protocol::wire::{
    CallFunctionRequest, ComponentInvocationRequest, FailureCode, InvocationEvent,
    ReadResourceRequest, SubscribeResourceRequest, component_invocation_request, invocation_event,
};
use reframe_store_sdk::{pack, unpack};

const HTTP_RESOURCE: &str = "reference.http.loopback_snapshot";
const COUNTER_RESOURCE: &str = "reference.streams.counter";

struct FakeHttp {
    calls: Rc<Cell<u32>>,
}

impl HttpClient for FakeHttp {
    fn get(&self, target: &HttpTarget) -> Result<HttpSnapshot, ResourceError> {
        self.calls.set(self.calls.get() + 1);
        Ok(HttpSnapshot {
            url: target.url().to_owned(),
            status_code: 200,
            content_type: "text/plain".to_owned(),
            body: b"loopback".to_vec(),
        })
    }
}

#[test]
fn injected_http_boundary_returns_a_typed_unary_value() {
    let selector = LoopbackSelector {
        url: "http://localhost:8080/health".to_owned(),
        max_body_bytes: 1024,
    };
    let request = ComponentInvocationRequest {
        request_id: "16aaed2d-1f66-4c9e-9970-17a484a230e8".to_owned(),
        operation: Some(component_invocation_request::Operation::ReadResource(
            ReadResourceRequest {
                resource_id: HTTP_RESOURCE.to_owned(),
                selector: Some(pack(&selector).unwrap()),
            },
        )),
    };

    let calls = Rc::new(Cell::new(0));
    let invocation = invoke_with_http(
        &request.encode_to_vec(),
        FakeHttp {
            calls: Rc::clone(&calls),
        },
    )
    .unwrap();
    assert_eq!(calls.get(), 0, "invoke must not perform deferred HTTP I/O");
    let started = next_event(&invocation);
    assert!(matches!(
        started.event,
        Some(invocation_event::Event::Started(_))
    ));
    assert_eq!(calls.get(), 0, "Started must not perform deferred HTTP I/O");
    let mut events = vec![started, next_event(&invocation)];
    assert_eq!(
        calls.get(),
        1,
        "the first application pull performs HTTP once"
    );
    events.extend(collect(invocation));
    let value = events
        .iter()
        .find_map(|event| match event.event.as_ref() {
            Some(invocation_event::Event::Data(data)) => data.value.as_ref(),
            _ => None,
        })
        .unwrap();
    let snapshot = unpack::<LoopbackSnapshot>(value).unwrap();
    assert_eq!(snapshot.status_code, 200);
    assert_eq!(snapshot.body, b"loopback");
}

#[test]
fn subscription_produces_a_typed_ordered_stream() {
    let selector = CounterSelector {
        sample_count: 3,
        label: "test".to_owned(),
    };
    let request = ComponentInvocationRequest {
        request_id: "97e46418-7292-4190-9eeb-b0bc372cbd93".to_owned(),
        operation: Some(component_invocation_request::Operation::SubscribeResource(
            SubscribeResourceRequest {
                resource_id: COUNTER_RESOURCE.to_owned(),
                selector: Some(pack(&selector).unwrap()),
            },
        )),
    };

    let events = collect(invoke(&request.encode_to_vec()).unwrap());
    assert!(matches!(
        events.first().and_then(|event| event.event.as_ref()),
        Some(invocation_event::Event::Started(_))
    ));
    assert_eq!(
        events
            .iter()
            .filter(|event| matches!(event.event, Some(invocation_event::Event::Data(_))))
            .count(),
        3
    );
    let kinds = events
        .iter()
        .map(|event| match event.event.as_ref() {
            Some(invocation_event::Event::Started(_)) => "started",
            Some(invocation_event::Event::Data(_)) => "data",
            Some(invocation_event::Event::Progress(_)) => "progress",
            Some(invocation_event::Event::Complete(_)) => "complete",
            Some(invocation_event::Event::Failure(_)) => "failure",
            None => "missing",
        })
        .collect::<Vec<_>>();
    assert_eq!(
        kinds,
        [
            "started", "data", "progress", "data", "progress", "data", "progress", "complete"
        ]
    );
    assert!(matches!(
        events.last().and_then(|event| event.event.as_ref()),
        Some(invocation_event::Event::Complete(_))
    ));
    assert!(
        events
            .iter()
            .enumerate()
            .all(|(index, event)| event.sequence_number == index as u64)
    );
}

#[test]
fn normalize_label_function_returns_a_typed_value() {
    let input = NormalizeLabelInput {
        label: "  Semantic\tStore\nLabel  ".to_owned(),
    };
    let request = ComponentInvocationRequest {
        request_id: "b96602ce-2b95-4bf8-a1c8-71de9da5c3fd".to_owned(),
        operation: Some(component_invocation_request::Operation::CallFunction(
            CallFunctionRequest {
                function_id: NORMALIZE_LABEL_FUNCTION_ID.to_owned(),
                input: Some(pack(&input).unwrap()),
                idempotency_key: String::new(),
            },
        )),
    };

    let events = collect(invoke(&request.encode_to_vec()).unwrap());
    let value = events
        .iter()
        .find_map(|event| match event.event.as_ref() {
            Some(invocation_event::Event::Data(data)) => data.value.as_ref(),
            _ => None,
        })
        .expect("typed function output");
    let output = unpack::<NormalizeLabelOutput>(value).unwrap();

    assert_eq!(output.normalized_label, "Semantic Store Label");
    assert!(matches!(
        events.last().and_then(|event| event.event.as_ref()),
        Some(invocation_event::Event::Complete(_))
    ));
}

#[test]
fn normalize_label_rejects_a_resource_operation() {
    let input = NormalizeLabelInput {
        label: "Semantic Store".to_owned(),
    };
    let request = ComponentInvocationRequest {
        request_id: "ff9da389-b982-4981-9941-efb9bcc89202".to_owned(),
        operation: Some(component_invocation_request::Operation::ReadResource(
            ReadResourceRequest {
                resource_id: NORMALIZE_LABEL_FUNCTION_ID.to_owned(),
                selector: Some(pack(&input).unwrap()),
            },
        )),
    };

    let events = collect(invoke(&request.encode_to_vec()).unwrap());
    let failure = events
        .last()
        .and_then(|event| event.event.as_ref())
        .and_then(|event| match event {
            invocation_event::Event::Failure(failure) => Some(failure),
            _ => None,
        })
        .expect("operation mismatch failure");

    assert_eq!(failure.code, FailureCode::InvalidArgument as i32);
    assert!(failure.message.contains(NORMALIZE_LABEL_FUNCTION_ID));
    assert!(!failure.retryable);
    assert!(!events.iter().any(|event| matches!(
        event.event,
        Some(invocation_event::Event::Data(_)) | Some(invocation_event::Event::Complete(_))
    )));
}

fn collect(invocation: reframe_store_sdk::Invocation) -> Vec<InvocationEvent> {
    std::iter::from_fn(|| invocation.next().unwrap())
        .map(|bytes| InvocationEvent::decode(bytes.as_slice()).unwrap())
        .collect()
}

fn next_event(invocation: &reframe_store_sdk::Invocation) -> InvocationEvent {
    let bytes = invocation.next().unwrap().expect("next invocation event");
    InvocationEvent::decode(bytes.as_slice()).unwrap()
}
