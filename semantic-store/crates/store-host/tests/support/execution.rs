use anyhow::{Result, bail, ensure};
use reframe_reference_store::{
    CounterSample, CounterSelector, HttpSnapshot, HttpSnapshotSelector, LoopbackSelector,
    LoopbackSnapshot, NORMALIZE_LABEL_FUNCTION_ID, NormalizeLabelInput, NormalizeLabelOutput,
};
use reframe_store_protocol::wire::{
    CallFunctionRequest, CloseStoreRequest, InvocationEvent, ReadResourceRequest,
    SubscribeResourceRequest, envelope, invocation_event,
};
use reframe_store_sdk::{pack, unpack};
use tokio::time::{Duration, timeout};

use super::{TestClient, http::quick_server};

pub(crate) async fn read_loopback(client: &mut TestClient, session_id: &str) -> Result<()> {
    let body = b"semantic loopback";
    let (url, server) = quick_server(body).await?;
    let selector = LoopbackSelector {
        url,
        max_body_bytes: 4096,
    };
    let request_id = client
        .send(
            session_id,
            envelope::Message::ReadResourceRequest(ReadResourceRequest {
                resource_id: "reference.http.loopback_snapshot".to_owned(),
                selector: Some(pack(&selector)?),
            }),
        )
        .await?;
    let events = invocation_events(client, &request_id).await?;
    let value = data_values(&events)
        .into_iter()
        .next()
        .ok_or_else(|| anyhow::anyhow!("HTTP read returned no Data event"))?;
    let snapshot = unpack::<LoopbackSnapshot>(value)?;
    ensure!(
        snapshot.status_code == 200,
        "loopback HTTP status was not 200"
    );
    ensure!(
        snapshot.body == body,
        "loopback HTTP body did not round-trip"
    );
    timeout(Duration::from_secs(5), server).await???;
    Ok(())
}

pub(crate) async fn read_http_snapshot(client: &mut TestClient, session_id: &str) -> Result<()> {
    let body = b"general HTTP snapshot";
    let (url, server) = quick_server(body).await?;
    let snapshot = fetch_http_snapshot(client, session_id, url).await?;
    ensure!(snapshot.status_code == 200);
    ensure!(snapshot.body == body);
    timeout(Duration::from_secs(5), server).await???;
    Ok(())
}

pub(crate) async fn read_https_snapshot(client: &mut TestClient, session_id: &str) -> Result<()> {
    const ORDINARY_HTTPS_URL: &str = "https://example.com/";

    let snapshot = timeout(
        Duration::from_secs(15),
        fetch_http_snapshot(client, session_id, ORDINARY_HTTPS_URL.to_owned()),
    )
    .await
    .map_err(|_| anyhow::anyhow!("ordinary HTTPS conformance request timed out"))??;
    ensure!(snapshot.url == ORDINARY_HTTPS_URL);
    ensure!(
        snapshot.status_code == 200,
        "ordinary HTTPS status was not 200"
    );
    ensure!(
        snapshot.content_type.starts_with("text/html"),
        "ordinary HTTPS response did not carry HTML content"
    );
    ensure!(
        !snapshot.body.is_empty(),
        "ordinary HTTPS response body was empty"
    );
    Ok(())
}

async fn fetch_http_snapshot(
    client: &mut TestClient,
    session_id: &str,
    url: String,
) -> Result<HttpSnapshot> {
    let request_id = client
        .send(
            session_id,
            envelope::Message::ReadResourceRequest(ReadResourceRequest {
                resource_id: "reference.http.snapshot".to_owned(),
                selector: Some(pack(&HttpSnapshotSelector {
                    url,
                    max_body_bytes: 4096,
                })?),
            }),
        )
        .await?;
    let events = invocation_events(client, &request_id).await?;
    ensure!(
        matches!(
            events.last().and_then(|event| event.event.as_ref()),
            Some(invocation_event::Event::Complete(_))
        ),
        "HTTP snapshot did not finish with Complete"
    );
    let value = data_values(&events)
        .into_iter()
        .next()
        .ok_or_else(|| anyhow::anyhow!("HTTP snapshot returned no Data event"))?;
    unpack::<HttpSnapshot>(value).map_err(Into::into)
}

pub(crate) async fn subscribe_counter(client: &mut TestClient, session_id: &str) -> Result<()> {
    let selector = CounterSelector {
        sample_count: 3,
        label: "conformance".to_owned(),
    };
    let request_id = client
        .send(
            session_id,
            envelope::Message::SubscribeResourceRequest(SubscribeResourceRequest {
                resource_id: "reference.streams.counter".to_owned(),
                selector: Some(pack(&selector)?),
            }),
        )
        .await?;
    let events = invocation_events(client, &request_id).await?;
    let samples = data_values(&events)
        .into_iter()
        .map(unpack::<CounterSample>)
        .collect::<Result<Vec<_>, _>>()?;
    ensure!(
        samples.iter().map(|sample| sample.index).eq(0..3),
        "counter subscription values are not ordered"
    );
    ensure!(
        events
            .iter()
            .filter(|event| matches!(event.event, Some(invocation_event::Event::Progress(_))))
            .count()
            == 3,
        "counter subscription progress is incomplete"
    );
    Ok(())
}

pub(crate) async fn call_normalize_label(client: &mut TestClient, session_id: &str) -> Result<()> {
    let input = NormalizeLabelInput {
        label: "  Semantic\tStore\nLabel  ".to_owned(),
    };
    let request_id = client
        .send(
            session_id,
            envelope::Message::CallFunctionRequest(CallFunctionRequest {
                function_id: NORMALIZE_LABEL_FUNCTION_ID.to_owned(),
                input: Some(pack(&input)?),
                idempotency_key: String::new(),
            }),
        )
        .await?;
    let events = invocation_events(client, &request_id).await?;
    let value = data_values(&events)
        .into_iter()
        .next()
        .ok_or_else(|| anyhow::anyhow!("NormalizeLabel returned no Data event"))?;
    let output = unpack::<NormalizeLabelOutput>(value)?;
    ensure!(
        output.normalized_label == "Semantic Store Label",
        "NormalizeLabel returned the wrong typed output"
    );
    Ok(())
}

pub(crate) async fn close_store(client: &mut TestClient, session_id: &str) -> Result<()> {
    let response = client
        .request(
            session_id,
            envelope::Message::CloseStoreRequest(CloseStoreRequest {}),
        )
        .await?;
    match response.message {
        Some(envelope::Message::CloseStoreResponse(close)) => {
            ensure!(close.closed, "CloseStore did not close the session");
            Ok(())
        }
        _ => bail!("CloseStore did not return CloseStoreResponse"),
    }
}

async fn invocation_events(
    client: &mut TestClient,
    request_id: &str,
) -> Result<Vec<InvocationEvent>> {
    let mut events = Vec::new();
    loop {
        let envelope = client.receive().await?;
        ensure!(
            envelope.request_id == request_id,
            "invocation response was miscorrelated"
        );
        let Some(envelope::Message::InvocationEvent(event)) = envelope.message else {
            bail!("execution did not return an InvocationEvent");
        };
        ensure!(
            event.sequence_number == events.len() as u64,
            "event sequence has a gap"
        );
        let terminal = matches!(
            event.event,
            Some(invocation_event::Event::Complete(_) | invocation_event::Event::Failure(_))
        );
        events.push(event);
        if terminal {
            return Ok(events);
        }
    }
}

fn data_values(events: &[InvocationEvent]) -> Vec<&prost_types::Any> {
    events
        .iter()
        .filter_map(|event| match event.event.as_ref() {
            Some(invocation_event::Event::Data(data)) => data.value.as_ref(),
            _ => None,
        })
        .collect()
}
