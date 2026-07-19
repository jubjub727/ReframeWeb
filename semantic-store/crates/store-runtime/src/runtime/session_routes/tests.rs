use std::{
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::Duration,
};

use async_trait::async_trait;
use reframe_store_protocol::{CURRENT_PROTOCOL_VERSION, wire::Envelope};
use tokio::sync::{Mutex, Notify, Semaphore, mpsc};

use crate::{
    InvocationMode, ResponseSink, ResponseSinkError, invocation::InvocationOutput,
    session::SessionState,
};

use super::*;

struct BlockingSink {
    entered: mpsc::UnboundedSender<()>,
}

#[async_trait]
impl ResponseSink for BlockingSink {
    async fn send(&self, _envelope: Envelope) -> Result<(), ResponseSinkError> {
        let _ = self.entered.send(());
        std::future::pending().await
    }
}

struct DropNotice(Arc<Notify>);

impl Drop for DropNotice {
    fn drop(&mut self) {
        self.0.notify_one();
    }
}

#[tokio::test]
async fn aborted_cancel_response_reclaims_session_and_global_capacity() {
    let request_id = uuid::Uuid::new_v4().to_string();
    let state = Arc::new(SessionState::new(8));
    let slots = Arc::new(Semaphore::new(1));
    let permit = Arc::clone(&slots).try_acquire_owned().unwrap();
    let (entered_tx, mut entered_rx) = mpsc::unbounded_channel();
    let sink: Arc<dyn ResponseSink> = Arc::new(BlockingSink {
        entered: entered_tx,
    });
    let finished = Arc::new(AtomicBool::new(false));
    let output = Arc::new(Mutex::new(InvocationOutput::new(
        request_id.clone(),
        uuid::Uuid::new_v4().to_string(),
        CURRENT_PROTOCOL_VERSION,
        InvocationMode::Unary,
        Arc::clone(&sink),
        Duration::from_secs(30),
        Arc::clone(&finished),
    )));
    let guest_dropped = Arc::new(Notify::new());
    let drop_notice = DropNotice(Arc::clone(&guest_dropped));
    let task = tokio::spawn(async move {
        let _drop_notice = drop_notice;
        std::future::pending::<()>().await;
    });
    let active = Arc::new(ActiveInvocation::new(
        output,
        task,
        Arc::clone(&finished),
        permit,
    ));
    assert!(state.try_add_invocation(request_id.clone(), Arc::clone(&active), 1));
    drop(active);

    let invocation = state.invocation(&request_id).unwrap();
    let cancel_state = Arc::clone(&state);
    let cancel_request_id = request_id.clone();
    let response_sink = Arc::clone(&sink);
    let cancel_handler = tokio::spawn(async move {
        assert_eq!(
            cancel_supervised(cancel_state, cancel_request_id, invocation).await,
            CancelDisposition::Cancelled
        );
        response_sink.send(Envelope::default()).await.unwrap();
    });

    tokio::time::timeout(Duration::from_secs(1), guest_dropped.notified())
        .await
        .expect("guest task was not hard-cancelled");
    for _ in 0..2 {
        tokio::time::timeout(Duration::from_secs(1), entered_rx.recv())
            .await
            .expect("response sink was not entered")
            .expect("response sink tracker closed");
    }
    cancel_handler.abort();
    let _ = cancel_handler.await;

    assert!(state.invocation(&request_id).is_none());
    assert_eq!(state.active_invocation_count(), 0);
    assert_eq!(slots.available_permits(), 1);
    assert!(!finished.load(Ordering::Acquire));
    let _replacement_permit = slots.try_acquire_owned().unwrap();
}
