use std::panic::{AssertUnwindSafe, catch_unwind};

use prost::Message;
use reframe_reference_store::{DiagnosticTrapInput, invoke};
use reframe_store_protocol::wire::{
    CallFunctionRequest, ComponentInvocationRequest, InvocationEvent, component_invocation_request,
    invocation_event,
};
use reframe_store_sdk::pack;

#[test]
fn diagnostic_trap_occurs_only_after_started_pull() {
    let request = ComponentInvocationRequest {
        request_id: "5104340b-321c-4a62-9e92-70b34b64f56f".to_owned(),
        operation: Some(component_invocation_request::Operation::CallFunction(
            CallFunctionRequest {
                function_id: "reference.diagnostics.trap".to_owned(),
                input: Some(pack(&DiagnosticTrapInput {}).unwrap()),
                idempotency_key: String::new(),
            },
        )),
    };
    let invocation = invoke(&request.encode_to_vec()).unwrap();
    let started = InvocationEvent::decode(
        invocation
            .next()
            .unwrap()
            .expect("Started event")
            .as_slice(),
    )
    .unwrap();
    assert!(matches!(
        started.event,
        Some(invocation_event::Event::Started(_))
    ));

    let trapped = catch_unwind(AssertUnwindSafe(|| invocation.next()));
    assert!(
        trapped.is_err(),
        "diagnostic source did not trap on its pull"
    );
}
