use anyhow::{Result, bail, ensure};
use reframe_reference_store::DiagnosticTrapInput;
use reframe_store_protocol::wire::{CallFunctionRequest, FailureCode, envelope, invocation_event};
use reframe_store_sdk::pack;

use super::TestClient;

pub(crate) async fn diagnostic_trap_is_isolated(
    client: &mut TestClient,
    session_id: &str,
) -> Result<()> {
    let request_id = client
        .send(
            session_id,
            envelope::Message::CallFunctionRequest(CallFunctionRequest {
                function_id: "reference.diagnostics.trap".to_owned(),
                input: Some(pack(&DiagnosticTrapInput {})?),
                idempotency_key: String::new(),
            }),
        )
        .await?;
    let mut started = false;
    loop {
        let response = client.receive().await?;
        ensure!(
            response.request_id == request_id,
            "trap response was miscorrelated"
        );
        let Some(envelope::Message::InvocationEvent(event)) = response.message else {
            bail!("trap response was not an InvocationEvent");
        };
        match event.event {
            Some(invocation_event::Event::Started(_)) => {
                ensure!(!started && event.sequence_number == 0);
                started = true;
            }
            Some(invocation_event::Event::Failure(failure)) => {
                ensure!(started && event.sequence_number == 1);
                ensure!(
                    failure.code == FailureCode::Internal as i32,
                    "diagnostic trap did not become an Internal failure"
                );
                return Ok(());
            }
            _ => bail!("diagnostic trap emitted an unexpected event"),
        }
    }
}
