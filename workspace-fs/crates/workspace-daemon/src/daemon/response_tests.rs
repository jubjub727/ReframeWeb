use std::collections::HashMap;

use anyhow::Result;

use crate::protocol::{Request, Response};
use crate::store::Store;

use super::Daemon;
use super::idempotency::IdempotencyAction;

fn daemon(root: &std::path::Path) -> Result<Daemon> {
    Ok(Daemon {
        store: Store::open(root)?,
        residents: HashMap::new(),
        process_idempotency_requests: Default::default(),
        mounts: HashMap::new(),
    })
}

#[test]
fn oversized_mutation_response_is_completed_with_a_transportable_terminal_error() -> Result<()> {
    const TEST_LIMIT: usize = 2_048;
    let root =
        std::env::temp_dir().join(format!("reframe-response-limit-{}", Store::next_id("test")));
    let mut daemon = daemon(&root)?;
    let request: Request = serde_json::from_str(
        r#"{"request_id":"first","idempotency_key":"large-result","operation":"create_workspace","name":"test","session_id":"one","memory_sources":[],"scratch_paths":[]}"#,
    )?;
    assert!(matches!(
        daemon.begin_idempotent(&request),
        IdempotencyAction::Execute
    ));

    let response = daemon.finalize_response(
        &request,
        Response {
            request_id: request.request_id.clone(),
            ok: true,
            result: Some(serde_json::json!({"payload":"x".repeat(TEST_LIMIT * 2)})),
            error: None,
        },
        TEST_LIMIT,
    );
    assert!(!response.ok);
    assert_eq!(
        response.error.as_ref().expect("terminal error").code,
        "response_too_large"
    );
    assert!(serde_json::to_string(&response)?.len() <= TEST_LIMIT);

    let retry: Request = serde_json::from_str(
        r#"{"request_id":"retry","idempotency_key":"large-result","operation":"create_workspace","name":"test","session_id":"one","memory_sources":[],"scratch_paths":[]}"#,
    )?;
    let IdempotencyAction::Respond(replayed) = daemon.begin_idempotent(&retry) else {
        panic!("terminal response should have been completed durably");
    };
    assert_eq!(replayed.request_id, "retry");
    assert_eq!(
        replayed.error.expect("replayed error").code,
        "response_too_large"
    );

    drop(daemon);
    std::fs::remove_dir_all(root)?;
    Ok(())
}
