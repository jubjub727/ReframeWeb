use std::io::Cursor;

use crate::protocol::{MemorySourceDto, Operation};

use super::framing::read_frame;

fn framed(payload: &[u8]) -> Vec<u8> {
    let mut frame = (payload.len() as u32).to_le_bytes().to_vec();
    frame.extend_from_slice(payload);
    frame
}

fn rejected(payload: &[u8]) -> crate::protocol::Response {
    let error =
        read_frame(&mut Cursor::new(framed(payload))).expect_err("request should be rejected");
    error.client_response().expect("structured client error")
}

#[test]
fn top_level_unknown_fields_are_rejected() {
    let response = rejected(br#"{"request_id":"strict","operation":"hello","future":true}"#);
    assert_eq!(response.request_id, "strict");
    let error = response.error.expect("protocol error");
    assert_eq!(error.code, "invalid_request");
    assert_eq!(error.operation, "hello");
}

#[test]
fn nested_memory_source_unknown_fields_are_rejected() {
    let response = rejected(
        br#"{"request_id":"strict","operation":"create_workspace","name":"test","session_id":"one","memory_sources":[{"source_kind":"directory","memory_id":"memory","source_path":"source","future":true}],"scratch_paths":[]}"#,
    );
    assert_eq!(
        response.error.expect("protocol error").code,
        "invalid_request"
    );
}

#[test]
fn valid_tagged_operations_and_sources_still_decode() {
    let payload = br#"{"request_id":"valid","operation":"create_workspace","name":"test","session_id":"one","memory_sources":[{"source_kind":"directory","memory_id":"memory","source_path":"source"}],"scratch_paths":[]}"#;
    let request = read_frame(&mut Cursor::new(framed(payload)))
        .expect("valid request")
        .expect("request frame");
    let Operation::CreateWorkspace { memory_sources, .. } = request.operation else {
        panic!("wrong tagged operation");
    };
    assert!(matches!(
        memory_sources.as_slice(),
        [MemorySourceDto::Directory { memory_id, .. }] if memory_id == "memory"
    ));
}
