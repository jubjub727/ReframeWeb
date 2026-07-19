use std::sync::Arc;
use std::time::Duration;

use async_trait::async_trait;
use reframe_store_protocol::wire::Envelope;
use tokio::io::{AsyncWriteExt as _, duplex};
use tokio::sync::{Notify, Semaphore, mpsc};
use tokio_util::sync::CancellationToken;

use super::{ConnectionEnd, EnvelopeSender, Handler, run_connection_with_shared_budgets};
use crate::{HandlerError, TransportConfig, encode_frame};

struct BlockingHandler {
    started: mpsc::UnboundedSender<String>,
    release_first: Arc<Notify>,
    release_second: Arc<Notify>,
}

#[async_trait]
impl Handler for BlockingHandler {
    async fn handle(
        &self,
        envelope: Envelope,
        _outbound: EnvelopeSender,
    ) -> Result<(), HandlerError> {
        self.started
            .send(envelope.request_id.clone())
            .map_err(|_| HandlerError::message("test receiver closed"))?;
        match envelope.request_id.as_str() {
            "first" => self.release_first.notified().await,
            "second" => self.release_second.notified().await,
            other => return Err(HandlerError::message(format!("unexpected request {other}"))),
        }
        Ok(())
    }
}

fn request(id: &str) -> Envelope {
    Envelope {
        request_id: id.to_owned(),
        ..Envelope::default()
    }
}

#[tokio::test]
async fn shared_admission_permit_lives_until_the_handler_finishes() {
    const FRAME_LIMIT: usize = 1_024;

    let config = TransportConfig::new(FRAME_LIMIT, 4, 4, 2)
        .unwrap()
        .with_inbound_byte_budget(FRAME_LIMIT)
        .unwrap()
        .with_read_timeout(Duration::from_secs(1))
        .unwrap();
    let budget = Arc::new(Semaphore::new(config.inbound_byte_budget()));
    let outbound_budget = Arc::new(Semaphore::new(config.aggregate_outbound_byte_budget()));
    let (started_tx, mut started_rx) = mpsc::unbounded_channel();
    let release_first = Arc::new(Notify::new());
    let release_second = Arc::new(Notify::new());
    let handler = Arc::new(BlockingHandler {
        started: started_tx,
        release_first: Arc::clone(&release_first),
        release_second: Arc::clone(&release_second),
    });

    let (server_first, mut client_first) = duplex(4_096);
    let first_task = tokio::spawn(run_connection_with_shared_budgets(
        server_first,
        Arc::clone(&handler),
        config.clone(),
        CancellationToken::new(),
        Arc::clone(&budget),
        Arc::clone(&outbound_budget),
    ));
    client_first
        .write_all(&encode_frame(&request("first"), FRAME_LIMIT).unwrap())
        .await
        .unwrap();
    assert_eq!(started_rx.recv().await.as_deref(), Some("first"));
    assert_eq!(budget.available_permits(), 0);

    let (server_second, mut client_second) = duplex(4_096);
    let second_task = tokio::spawn(run_connection_with_shared_budgets(
        server_second,
        handler,
        config,
        CancellationToken::new(),
        Arc::clone(&budget),
        outbound_budget,
    ));
    client_second
        .write_all(&encode_frame(&request("second"), FRAME_LIMIT).unwrap())
        .await
        .unwrap();
    assert!(
        tokio::time::timeout(Duration::from_millis(30), started_rx.recv())
            .await
            .is_err(),
        "a second connection must share the exhausted admission budget"
    );

    release_first.notify_one();
    assert_eq!(
        tokio::time::timeout(Duration::from_secs(1), started_rx.recv())
            .await
            .unwrap()
            .as_deref(),
        Some("second")
    );
    assert_eq!(budget.available_permits(), 0);

    release_second.notify_one();
    client_first.shutdown().await.unwrap();
    client_second.shutdown().await.unwrap();
    assert_eq!(
        first_task.await.unwrap().unwrap(),
        ConnectionEnd::PeerClosed
    );
    assert_eq!(
        second_task.await.unwrap().unwrap(),
        ConnectionEnd::PeerClosed
    );
    assert_eq!(budget.available_permits(), FRAME_LIMIT);
}

#[tokio::test]
async fn shutdown_releases_a_partial_frames_admission_permit() {
    const FRAME_LIMIT: usize = 16;

    let config = TransportConfig::new(FRAME_LIMIT, 1, 1, 1)
        .unwrap()
        .with_inbound_byte_budget(FRAME_LIMIT)
        .unwrap();
    let inbound_budget = Arc::new(Semaphore::new(FRAME_LIMIT));
    let outbound_budget = Arc::new(Semaphore::new(config.aggregate_outbound_byte_budget()));
    let (started_tx, _started_rx) = mpsc::unbounded_channel();
    let handler = Arc::new(BlockingHandler {
        started: started_tx,
        release_first: Arc::new(Notify::new()),
        release_second: Arc::new(Notify::new()),
    });
    let (server, mut client) = duplex(16);
    let shutdown = CancellationToken::new();
    let task = tokio::spawn(run_connection_with_shared_budgets(
        server,
        handler,
        config,
        shutdown.clone(),
        Arc::clone(&inbound_budget),
        outbound_budget,
    ));

    client.write_all(&1_u32.to_be_bytes()).await.unwrap();
    tokio::time::timeout(Duration::from_secs(1), async {
        while inbound_budget.available_permits() != 0 {
            tokio::task::yield_now().await;
        }
    })
    .await
    .expect("the partial payload must acquire admission before allocation");

    shutdown.cancel();
    assert_eq!(task.await.unwrap().unwrap(), ConnectionEnd::Shutdown);
    assert_eq!(inbound_budget.available_permits(), FRAME_LIMIT);
}
