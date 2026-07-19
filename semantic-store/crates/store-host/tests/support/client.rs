use std::time::Duration;

use anyhow::{Context, Result, bail};
use reframe_store_protocol::{
    CURRENT_PROTOCOL_VERSION,
    wire::{Envelope, envelope},
};
use reframe_store_transport::{
    DEFAULT_MAX_FRAME_SIZE, LocalEndpoint, LocalStream, connect, read_envelope, write_envelope,
};
use tokio::time::{Instant, sleep, timeout};

pub(crate) struct TestClient {
    stream: LocalStream,
}

impl TestClient {
    pub(crate) async fn connect(endpoint: &LocalEndpoint) -> Result<Self> {
        let deadline = Instant::now() + Duration::from_secs(10);
        loop {
            match connect(endpoint).await {
                Ok(stream) => return Ok(Self { stream }),
                Err(error) if Instant::now() >= deadline => {
                    return Err(error).context("could not connect to the local Store host");
                }
                Err(_) => {}
            }
            sleep(Duration::from_millis(20)).await;
        }
    }

    pub(crate) async fn request(
        &mut self,
        session_id: &str,
        message: envelope::Message,
    ) -> Result<Envelope> {
        let request_id = self.send(session_id, message).await?;
        let response = self.receive().await?;
        if response.request_id != request_id {
            bail!(
                "response {} did not match request {request_id}",
                response.request_id
            );
        }
        Ok(response)
    }

    pub(crate) async fn send(
        &mut self,
        session_id: &str,
        message: envelope::Message,
    ) -> Result<String> {
        let request_id = uuid::Uuid::new_v4().to_string();
        let envelope = Envelope {
            protocol_version: Some(CURRENT_PROTOCOL_VERSION),
            session_id: session_id.to_owned(),
            request_id: request_id.clone(),
            sequence_number: 0,
            message: Some(message),
        };
        write_envelope(&mut self.stream, &envelope, DEFAULT_MAX_FRAME_SIZE)
            .await
            .context("could not write request frame")?;
        Ok(request_id)
    }

    pub(crate) async fn receive(&mut self) -> Result<Envelope> {
        timeout(
            Duration::from_secs(10),
            read_envelope(&mut self.stream, DEFAULT_MAX_FRAME_SIZE),
        )
        .await
        .context("timed out waiting for response frame")??
        .context("Store host closed the local connection")
    }
}
