mod support;

use std::{sync::Arc, time::Duration};

use anyhow::{Context, Result, ensure};
use reframe_store_host::{HostRegistrationError, StoreHost};
use reframe_store_protocol::wire::{ErrorCode, GetStoreCardRequest, envelope};
use reframe_store_runtime::{EngineConfig, RuntimeConfig};
use reframe_store_transport::{LocalEndpoint, TransportConfig};
use tokio::time::timeout;
use tokio_util::sync::CancellationToken;

use support::{
    TestClient, browse_and_inspect_schema, call_normalize_label,
    cancel_blocked_http_without_affecting_peer, close_store, diagnostic_trap_is_isolated,
    expect_stale_catalog_cursor, first_catalog_cursor, open_and_inspect,
    package_with_schema_padding, package_with_updated_topic, read_http_snapshot,
    read_https_snapshot, read_loopback, reference_package, request_open, store_card_revision,
    subscribe_counter,
};

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
#[ignore = "build the wasm32-unknown-unknown reference component before running conformance"]
async fn real_reference_store_conforms_over_local_transport() -> Result<()> {
    let package = reference_package()?;
    let oversized_package = package_with_schema_padding(&package, 3 * 1024 * 1024)?;
    let updated_package = package_with_updated_topic(&package)?;
    let runtime_config = RuntimeConfig::default()
        .with_max_sessions(1)?
        .with_max_component_event_bytes(64 * 1024)?;
    let transport_config = TransportConfig::default().with_max_frame_size(2 * 1024 * 1024)?;
    let host = Arc::new(
        StoreHost::new_with_transport(
            [package],
            EngineConfig::default(),
            runtime_config,
            transport_config,
        )
        .await?,
    );
    let service_name = format!("reframe-conformance-{}", uuid::Uuid::new_v4().simple());
    let endpoint = LocalEndpoint::for_service(&service_name)?;

    let frame_error = host
        .register(oversized_package)
        .await
        .expect_err("post-construction registration must preserve the frame invariant");
    match frame_error {
        HostRegistrationError::Frame(error) => {
            ensure!(
                error.configured() == 2 * 1024 * 1024,
                "reported frame limit must be the configured value"
            );
            ensure!(
                error.required() > error.configured(),
                "required frame limit must exceed the rejected configuration"
            );
        }
        other => anyhow::bail!("expected a frame-limit registration error, got: {other}"),
    }

    let shutdown = CancellationToken::new();
    let server_host = Arc::clone(&host);
    let server_endpoint = endpoint.clone();
    let server_shutdown = shutdown.clone();
    let server =
        tokio::spawn(async move { server_host.serve(&server_endpoint, server_shutdown).await });

    let mut owner = TestClient::connect(&endpoint).await?;
    let owned_session = open_and_inspect(&mut owner)
        .await
        .context("could not open the connection-owned test session")?;
    let mut other_connection = TestClient::connect(&endpoint).await?;
    let foreign_response = other_connection
        .request(
            &owned_session,
            envelope::Message::GetStoreCardRequest(GetStoreCardRequest {}),
        )
        .await
        .context("could not test a foreign connection against the owned session")?;
    ensure!(
        matches!(
            foreign_response.message,
            Some(envelope::Message::Error(error))
                if error.code == ErrorCode::InvalidSession as i32
        ),
        "a live connection could use another connection's session"
    );
    drop(owner);
    let recovered_session = timeout(Duration::from_secs(3), async {
        loop {
            let response = request_open(&mut other_connection)
                .await
                .context("could not retry OpenStore after the owner disconnected")?;
            match response.message {
                Some(envelope::Message::OpenStoreResponse(_)) => {
                    break Ok::<_, anyhow::Error>(response.session_id);
                }
                Some(envelope::Message::Error(error))
                    if error.code == ErrorCode::RuntimeError as i32 && error.retryable =>
                {
                    tokio::time::sleep(Duration::from_millis(10)).await;
                }
                other => {
                    anyhow::bail!("unexpected response while awaiting a free session: {other:?}")
                }
            }
        }
    })
    .await
    .context("connection loss did not reclaim its owned session")??;
    close_store(&mut other_connection, &recovered_session)
        .await
        .context("could not close the recovered session")?;
    let mut client = other_connection;
    let session_id = open_and_inspect(&mut client)
        .await
        .context("could not open the main conformance session")?;
    browse_and_inspect_schema(&mut client, &session_id).await?;
    read_loopback(&mut client, &session_id).await?;
    read_http_snapshot(&mut client, &session_id).await?;
    read_https_snapshot(&mut client, &session_id).await?;
    call_normalize_label(&mut client, &session_id).await?;
    subscribe_counter(&mut client, &session_id).await?;
    cancel_blocked_http_without_affecting_peer(&mut client, &session_id).await?;
    diagnostic_trap_is_isolated(&mut client, &session_id).await?;
    call_normalize_label(&mut client, &session_id).await?;
    let old_catalog_cursor = first_catalog_cursor(&mut client, &session_id).await?;
    let original_revision = store_card_revision(&mut client, &session_id).await?;
    host.register(updated_package).await?;
    ensure!(
        store_card_revision(&mut client, &session_id).await? == original_revision,
        "an active session changed Store revision during hot registration"
    );
    close_store(&mut client, &session_id).await?;
    let updated_open = request_open(&mut client).await?;
    let updated_session_id = updated_open.session_id;
    let updated_revision = match updated_open.message {
        Some(envelope::Message::OpenStoreResponse(open)) => open.catalog_revision,
        other => anyhow::bail!("updated Store did not open: {other:?}"),
    };
    ensure!(
        updated_revision != original_revision,
        "new sessions did not observe the updated catalog revision"
    );
    expect_stale_catalog_cursor(&mut client, &updated_session_id, old_catalog_cursor).await?;
    close_store(&mut client, &updated_session_id).await?;
    drop(client);

    shutdown.cancel();
    let server_result = timeout(Duration::from_secs(10), server)
        .await
        .context("Store host did not shut down")?;
    server_result.context("Store host task panicked")??;
    Ok(())
}
