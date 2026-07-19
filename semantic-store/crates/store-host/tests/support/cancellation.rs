use anyhow::{Result, bail, ensure};
use reframe_reference_store::{LoopbackSelector, LoopbackSnapshot};
use reframe_store_protocol::wire::{
    CancelInvocationRequest, CancellationState, FailureCode, InvocationEvent, ReadResourceRequest,
    envelope, invocation_event,
};
use reframe_store_sdk::{pack, unpack};
use tokio::time::{Duration, timeout};

use super::{
    TestClient,
    http::{controlled_server, slow_server},
};

pub(crate) async fn cancel_blocked_http_without_affecting_peer(
    client: &mut TestClient,
    session_id: &str,
) -> Result<()> {
    let (target_url, target_accepted, target_server) = slow_server().await?;
    let target_id = send_http(client, session_id, target_url).await?;
    timeout(Duration::from_secs(5), target_accepted).await??;

    let peer_body = b"peer survived cancellation";
    let (peer_url, peer_accepted, release_peer, peer_server) = controlled_server(peer_body).await?;
    let peer_id = send_http(client, session_id, peer_url).await?;
    timeout(Duration::from_secs(5), peer_accepted).await??;
    let peer_started = receive_both_started(client, &target_id, &peer_id).await?;

    let cancel_id = client
        .send(
            session_id,
            envelope::Message::CancelInvocationRequest(CancelInvocationRequest {
                target_request_id: target_id.clone(),
            }),
        )
        .await?;
    receive_cancellation(client, &target_id, &cancel_id).await?;

    let _ = release_peer.send(());
    let peer_events = receive_peer_completion(client, &peer_id, peer_started).await?;
    let value = peer_events
        .iter()
        .find_map(|event| match event.event.as_ref() {
            Some(invocation_event::Event::Data(data)) => data.value.as_ref(),
            _ => None,
        })
        .ok_or_else(|| anyhow::anyhow!("peer HTTP invocation returned no Data event"))?;
    ensure!(
        unpack::<LoopbackSnapshot>(value)?.body == peer_body,
        "peer Wasmtime store was damaged by target cancellation"
    );

    target_server.abort();
    let _ = target_server.await;
    timeout(Duration::from_secs(5), peer_server).await???;
    Ok(())
}

async fn send_http(client: &mut TestClient, session_id: &str, url: String) -> Result<String> {
    client
        .send(
            session_id,
            envelope::Message::ReadResourceRequest(ReadResourceRequest {
                resource_id: "reference.http.loopback_snapshot".to_owned(),
                selector: Some(pack(&LoopbackSelector {
                    url,
                    max_body_bytes: 1024,
                })?),
            }),
        )
        .await
}

async fn receive_both_started(
    client: &mut TestClient,
    target_id: &str,
    peer_id: &str,
) -> Result<InvocationEvent> {
    let mut target_started = false;
    let mut peer_started = None;
    while !target_started || peer_started.is_none() {
        let response = client.receive().await?;
        let Some(envelope::Message::InvocationEvent(event)) = response.message else {
            bail!("blocked invocation did not emit an InvocationEvent");
        };
        ensure!(
            matches!(event.event, Some(invocation_event::Event::Started(_))),
            "blocked invocation emitted an event after Started"
        );
        ensure!(
            event.sequence_number == 0,
            "blocked invocation Started sequence was not zero"
        );
        if response.request_id == target_id {
            target_started = true;
        } else if response.request_id == peer_id {
            peer_started = Some(event);
        } else {
            bail!("unexpected response while awaiting blocked invocations");
        }
    }
    Ok(peer_started.expect("peer Started was observed"))
}

async fn receive_cancellation(
    client: &mut TestClient,
    target_id: &str,
    cancel_id: &str,
) -> Result<()> {
    let mut cancelled = false;
    let mut acknowledged = false;
    while !cancelled || !acknowledged {
        let response = client.receive().await?;
        match (response.request_id.as_str(), response.message) {
            (id, Some(envelope::Message::InvocationEvent(event))) if id == target_id => {
                let Some(invocation_event::Event::Failure(failure)) = event.event else {
                    bail!("cancelled HTTP invocation emitted an unexpected event");
                };
                ensure!(
                    event.sequence_number == 1,
                    "cancelled HTTP invocation terminal sequence was not one"
                );
                ensure!(failure.code == FailureCode::Cancelled as i32);
                cancelled = true;
            }
            (id, Some(envelope::Message::CancelInvocationResponse(cancel))) if id == cancel_id => {
                ensure!(cancel.state == CancellationState::Cancelled as i32);
                acknowledged = true;
            }
            (id, _) => bail!("unexpected response {id} while cancelling invocation"),
        }
    }
    Ok(())
}

async fn receive_peer_completion(
    client: &mut TestClient,
    peer_id: &str,
    started: InvocationEvent,
) -> Result<Vec<InvocationEvent>> {
    let mut events = vec![started];
    loop {
        let response = client.receive().await?;
        ensure!(
            response.request_id == peer_id,
            "peer response was miscorrelated"
        );
        let Some(envelope::Message::InvocationEvent(event)) = response.message else {
            bail!("peer response was not an InvocationEvent");
        };
        ensure!(event.sequence_number == events.len() as u64);
        let terminal = matches!(event.event, Some(invocation_event::Event::Complete(_)));
        ensure!(
            !matches!(event.event, Some(invocation_event::Event::Failure(_))),
            "peer invocation failed after target cancellation"
        );
        events.push(event);
        if terminal {
            return Ok(events);
        }
    }
}
