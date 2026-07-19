use std::sync::Arc;
use std::time::Duration;

use async_trait::async_trait;
use reframe_store_protocol::wire::Envelope;
use reframe_store_transport::{
    ConnectionEnd, ConnectionId, EnvelopeSender, Handler, HandlerError, TransportConfig,
    run_connection,
};
use tokio::io::{AsyncWriteExt as _, duplex};
use tokio::sync::{Notify, mpsc};
use tokio_util::sync::CancellationToken;

fn envelope(index: usize) -> Envelope {
    Envelope {
        request_id: format!("request-{index:02}"),
        ..Envelope::default()
    }
}

struct NeverCalled;

#[async_trait]
impl Handler for NeverCalled {
    async fn handle(
        &self,
        _envelope: Envelope,
        _outbound: EnvelopeSender,
    ) -> Result<(), HandlerError> {
        panic!("handler should not be called")
    }
}

#[tokio::test]
async fn cancellation_cleanly_shuts_down_the_writer() {
    let (server_stream, mut client_stream) = duplex(64);
    let shutdown = CancellationToken::new();
    let task = tokio::spawn(run_connection(
        server_stream,
        Arc::new(NeverCalled),
        TransportConfig::default(),
        shutdown.clone(),
    ));
    shutdown.cancel();

    assert_eq!(task.await.unwrap().unwrap(), ConnectionEnd::Shutdown);
    let mut byte = [0_u8; 1];
    assert_eq!(
        tokio::io::AsyncReadExt::read(&mut client_stream, &mut byte)
            .await
            .unwrap(),
        0
    );
}

struct Fails;

#[async_trait]
impl Handler for Fails {
    async fn handle(
        &self,
        _envelope: Envelope,
        _outbound: EnvelopeSender,
    ) -> Result<(), HandlerError> {
        Err(HandlerError::message("expected failure"))
    }
}

#[tokio::test]
async fn handler_failure_terminates_its_connection() {
    let (server_stream, mut client_stream) = duplex(128);
    let task = tokio::spawn(run_connection(
        server_stream,
        Arc::new(Fails),
        TransportConfig::default(),
        CancellationToken::new(),
    ));
    let frame = reframe_store_transport::encode_frame(&envelope(1), 1024).unwrap();
    client_stream.write_all(&frame).await.unwrap();

    assert!(matches!(
        task.await.unwrap(),
        Err(reframe_store_transport::ConnectionError::Handler(_))
    ));
}

struct LargeResponse {
    queued: Arc<Notify>,
}

#[async_trait]
impl Handler for LargeResponse {
    async fn handle(
        &self,
        mut envelope: Envelope,
        outbound: EnvelopeSender,
    ) -> Result<(), HandlerError> {
        envelope.session_id = "x".repeat(256 * 1024);
        outbound.send(&envelope).await.map_err(HandlerError::new)?;
        self.queued.notify_one();
        Ok(())
    }
}

#[tokio::test]
async fn shutdown_interrupts_a_writer_blocked_on_a_peer() {
    let (server_stream, mut client_stream) = duplex(64);
    let queued = Arc::new(Notify::new());
    let handler = Arc::new(LargeResponse {
        queued: Arc::clone(&queued),
    });
    let shutdown = CancellationToken::new();
    let config = TransportConfig::new(512 * 1024, 1, 1, 1)
        .unwrap()
        .with_write_timeout(Duration::from_millis(50))
        .unwrap();
    let task = tokio::spawn(run_connection(
        server_stream,
        handler,
        config,
        shutdown.clone(),
    ));
    let frame = reframe_store_transport::encode_frame(&envelope(1), 1024).unwrap();
    client_stream.write_all(&frame).await.unwrap();
    queued.notified().await;

    shutdown.cancel();
    let result = tokio::time::timeout(Duration::from_secs(1), task)
        .await
        .expect("shutdown must cancel a blocked write")
        .unwrap();
    assert!(matches!(
        result,
        Err(reframe_store_transport::ConnectionError::Writer(
            reframe_store_transport::FrameError::WriteTimedOut { .. }
        ))
    ));
}

struct Hangs {
    started: Arc<Notify>,
}

#[async_trait]
impl Handler for Hangs {
    async fn handle(
        &self,
        _envelope: Envelope,
        _outbound: EnvelopeSender,
    ) -> Result<(), HandlerError> {
        self.started.notify_one();
        std::future::pending().await
    }
}

#[tokio::test]
async fn handler_drain_is_bounded_during_shutdown() {
    let (server_stream, mut client_stream) = duplex(128);
    let started = Arc::new(Notify::new());
    let handler = Arc::new(Hangs {
        started: Arc::clone(&started),
    });
    let shutdown = CancellationToken::new();
    let config = TransportConfig::default()
        .with_handler_drain_timeout(Duration::from_millis(30))
        .unwrap();
    let task = tokio::spawn(run_connection(
        server_stream,
        handler,
        config,
        shutdown.clone(),
    ));
    let frame = reframe_store_transport::encode_frame(&envelope(1), 1024).unwrap();
    client_stream.write_all(&frame).await.unwrap();
    started.notified().await;
    shutdown.cancel();

    assert!(matches!(
        task.await.unwrap(),
        Err(reframe_store_transport::ConnectionError::HandlerDrainTimedOut { .. })
    ));
}

struct RetainsSender {
    retained: mpsc::UnboundedSender<EnvelopeSender>,
}

#[async_trait]
impl Handler for RetainsSender {
    async fn handle(
        &self,
        _envelope: Envelope,
        outbound: EnvelopeSender,
    ) -> Result<(), HandlerError> {
        self.retained
            .send(outbound)
            .map_err(|_| HandlerError::message("test receiver closed"))
    }
}

#[tokio::test]
async fn peer_eof_closes_senders_retained_by_async_invocations() {
    let (server_stream, mut client_stream) = duplex(128);
    let (retained_tx, mut retained_rx) = mpsc::unbounded_channel();
    let task = tokio::spawn(run_connection(
        server_stream,
        Arc::new(RetainsSender {
            retained: retained_tx,
        }),
        TransportConfig::default(),
        CancellationToken::new(),
    ));
    let frame = reframe_store_transport::encode_frame(&envelope(1), 1024).unwrap();
    client_stream.write_all(&frame).await.unwrap();
    let retained = retained_rx.recv().await.unwrap();
    client_stream.shutdown().await.unwrap();

    assert_eq!(
        tokio::time::timeout(Duration::from_secs(1), task)
            .await
            .expect("peer EOF must not be held open by response clones")
            .unwrap()
            .unwrap(),
        ConnectionEnd::PeerClosed
    );
    assert!(retained.is_closed());
}

struct TracksLifecycle {
    opened: mpsc::UnboundedSender<ConnectionId>,
    closed: mpsc::UnboundedSender<ConnectionId>,
}

#[async_trait]
impl Handler for TracksLifecycle {
    async fn handle(
        &self,
        _envelope: Envelope,
        outbound: EnvelopeSender,
    ) -> Result<(), HandlerError> {
        self.opened
            .send(outbound.connection_id())
            .map_err(|_| HandlerError::message("test lifecycle receiver closed"))
    }

    async fn connection_closed(&self, connection_id: ConnectionId) {
        let _ = self.closed.send(connection_id);
    }
}

#[tokio::test]
async fn peer_eof_runs_connection_cleanup_for_the_matching_identity() {
    let (server_stream, mut client_stream) = duplex(128);
    let (opened_tx, mut opened_rx) = mpsc::unbounded_channel();
    let (closed_tx, mut closed_rx) = mpsc::unbounded_channel();
    let task = tokio::spawn(run_connection(
        server_stream,
        Arc::new(TracksLifecycle {
            opened: opened_tx,
            closed: closed_tx,
        }),
        TransportConfig::default(),
        CancellationToken::new(),
    ));
    let frame = reframe_store_transport::encode_frame(&envelope(1), 1024).unwrap();
    client_stream.write_all(&frame).await.unwrap();
    let connection_id = opened_rx.recv().await.unwrap();
    client_stream.shutdown().await.unwrap();

    assert_eq!(task.await.unwrap().unwrap(), ConnectionEnd::PeerClosed);
    assert_eq!(closed_rx.recv().await, Some(connection_id));
}

#[tokio::test]
async fn aborting_the_connection_driver_still_runs_cleanup() {
    let (server_stream, mut client_stream) = duplex(128);
    let (opened_tx, mut opened_rx) = mpsc::unbounded_channel();
    let (closed_tx, mut closed_rx) = mpsc::unbounded_channel();
    let task = tokio::spawn(run_connection(
        server_stream,
        Arc::new(TracksLifecycle {
            opened: opened_tx,
            closed: closed_tx,
        }),
        TransportConfig::default(),
        CancellationToken::new(),
    ));
    let frame = reframe_store_transport::encode_frame(&envelope(1), 1024).unwrap();
    client_stream.write_all(&frame).await.unwrap();
    let connection_id = opened_rx.recv().await.unwrap();

    task.abort();
    let _ = task.await;
    assert_eq!(
        tokio::time::timeout(Duration::from_secs(1), closed_rx.recv())
            .await
            .expect("aborted connection did not run cleanup"),
        Some(connection_id)
    );
}
