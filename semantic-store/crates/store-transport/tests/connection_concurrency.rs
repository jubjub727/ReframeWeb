use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Duration;

use async_trait::async_trait;
use reframe_store_protocol::wire::Envelope;
use reframe_store_transport::{
    ConnectionEnd, EnvelopeSender, FrameReader, FrameWriter, Handler, HandlerError,
    TransportConfig, run_connection,
};
use tokio::io::duplex;
use tokio_util::sync::CancellationToken;

struct ConcurrentEcho {
    active: AtomicUsize,
    peak: AtomicUsize,
}

#[async_trait]
impl Handler for ConcurrentEcho {
    async fn handle(
        &self,
        envelope: Envelope,
        outbound: EnvelopeSender,
    ) -> Result<(), HandlerError> {
        let active = self.active.fetch_add(1, Ordering::SeqCst) + 1;
        self.peak.fetch_max(active, Ordering::SeqCst);
        tokio::time::sleep(Duration::from_millis(10)).await;
        outbound.send(&envelope).await.map_err(HandlerError::new)?;
        self.active.fetch_sub(1, Ordering::SeqCst);
        Ok(())
    }
}

fn envelope(index: usize) -> Envelope {
    Envelope {
        request_id: format!("request-{index:02}"),
        ..Envelope::default()
    }
}

#[tokio::test]
async fn concurrent_handlers_produce_only_complete_frames() {
    const COUNT: usize = 24;
    let handler = Arc::new(ConcurrentEcho {
        active: AtomicUsize::new(0),
        peak: AtomicUsize::new(0),
    });
    let observed_handler = Arc::clone(&handler);
    let config = TransportConfig::new(1024, 2, COUNT, 1).unwrap();
    let (server_stream, client_stream) = duplex(4096);
    let connection = tokio::spawn(run_connection(
        server_stream,
        handler,
        config,
        CancellationToken::new(),
    ));
    let (client_read, client_write) = tokio::io::split(client_stream);
    let mut writer = FrameWriter::new(client_write, 1024);
    let mut reader = FrameReader::new(client_read, 1024);

    for index in 0..COUNT {
        writer.write_envelope(&envelope(index)).await.unwrap();
    }
    writer.shutdown().await.unwrap();

    let mut response_ids = Vec::with_capacity(COUNT);
    while let Some(response) = reader.read_envelope().await.unwrap() {
        response_ids.push(response.request_id);
    }
    response_ids.sort();
    assert_eq!(
        response_ids,
        (0..COUNT)
            .map(|index| envelope(index).request_id)
            .collect::<Vec<_>>()
    );
    assert!(observed_handler.peak.load(Ordering::SeqCst) > 1);
    assert_eq!(
        connection.await.unwrap().unwrap(),
        ConnectionEnd::PeerClosed
    );
}
