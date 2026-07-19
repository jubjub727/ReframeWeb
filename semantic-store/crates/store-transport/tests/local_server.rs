#![cfg(windows)]

use std::sync::Arc;
use std::time::Duration;

use async_trait::async_trait;
use reframe_store_protocol::wire::Envelope;
use reframe_store_transport::{
    EnvelopeSender, FrameReader, FrameWriter, Handler, HandlerError, LocalEndpoint, LocalListener,
    TransportConfig, connect, serve_local,
};
use tokio_util::sync::CancellationToken;

struct Echo;

#[async_trait]
impl Handler for Echo {
    async fn handle(
        &self,
        envelope: Envelope,
        outbound: EnvelopeSender,
    ) -> Result<(), HandlerError> {
        outbound.send(&envelope).await.map_err(HandlerError::new)
    }
}

#[tokio::test]
async fn local_server_accepts_dispatches_and_shuts_down() {
    let endpoint = LocalEndpoint::for_service(&format!(
        "reframe-store-transport-server-test-{}",
        std::process::id()
    ))
    .unwrap();
    let listener = LocalListener::bind(&endpoint).unwrap();
    let shutdown = CancellationToken::new();
    let server = tokio::spawn(serve_local(
        listener,
        Arc::new(Echo),
        TransportConfig::default(),
        shutdown.clone(),
    ));

    let client = connect(&endpoint).await.unwrap();
    let (client_read, client_write) = tokio::io::split(client);
    let mut reader = FrameReader::new(client_read, 1024);
    let mut writer = FrameWriter::new(client_write, 1024);
    let request = Envelope {
        request_id: "server-round-trip".to_owned(),
        ..Envelope::default()
    };
    writer.write_envelope(&request).await.unwrap();
    assert_eq!(reader.read_envelope().await.unwrap(), Some(request));

    shutdown.cancel();
    tokio::time::timeout(Duration::from_secs(1), server)
        .await
        .expect("server shutdown must be bounded")
        .unwrap()
        .unwrap();
}
