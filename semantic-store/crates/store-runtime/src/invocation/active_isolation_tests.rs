use std::{
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::Duration,
};

use reframe_store_protocol::CURRENT_PROTOCOL_VERSION;
use tokio::sync::{Mutex, Notify, mpsc};

use crate::{ChannelSink, InvocationMode};

use super::{ActiveInvocation, CancelDisposition, InvocationOutput};

struct DropNotice(Arc<Notify>);

impl Drop for DropNotice {
    fn drop(&mut self) {
        self.0.notify_one();
    }
}

#[tokio::test]
async fn cancelling_blocked_guest_next_does_not_abort_peer_invocation() {
    let blocked_entered = Arc::new(Notify::new());
    let blocked_dropped = Arc::new(Notify::new());
    let blocked_finished = Arc::new(AtomicBool::new(false));
    let (blocked_sender, _blocked_receiver) = mpsc::channel(4);
    let blocked_output = Arc::new(Mutex::new(InvocationOutput::new(
        uuid::Uuid::new_v4().to_string(),
        uuid::Uuid::new_v4().to_string(),
        CURRENT_PROTOCOL_VERSION,
        InvocationMode::Subscription,
        Arc::new(ChannelSink::new(blocked_sender)),
        Duration::from_secs(1),
        Arc::clone(&blocked_finished),
    )));
    let blocked_task = tokio::spawn({
        let entered = Arc::clone(&blocked_entered);
        let drop_notice = DropNotice(Arc::clone(&blocked_dropped));
        async move {
            let _drop_notice = drop_notice;
            entered.notify_one();
            std::future::pending::<()>().await;
        }
    });

    let peer_release = Arc::new(Notify::new());
    let peer_done = Arc::new(Notify::new());
    let peer_finished = Arc::new(AtomicBool::new(false));
    let (peer_sender, _peer_receiver) = mpsc::channel(4);
    let peer_output = Arc::new(Mutex::new(InvocationOutput::new(
        uuid::Uuid::new_v4().to_string(),
        uuid::Uuid::new_v4().to_string(),
        CURRENT_PROTOCOL_VERSION,
        InvocationMode::Unary,
        Arc::new(ChannelSink::new(peer_sender)),
        Duration::from_secs(1),
        Arc::clone(&peer_finished),
    )));
    let peer_task = tokio::spawn({
        let release = Arc::clone(&peer_release);
        let done = Arc::clone(&peer_done);
        let finished = Arc::clone(&peer_finished);
        async move {
            release.notified().await;
            finished.store(true, Ordering::Release);
            done.notify_one();
        }
    });

    let permits = Arc::new(tokio::sync::Semaphore::new(2));
    let blocked = ActiveInvocation::new(
        blocked_output,
        blocked_task,
        blocked_finished,
        Arc::clone(&permits).try_acquire_owned().unwrap(),
    );
    let peer = ActiveInvocation::new(
        peer_output,
        peer_task,
        Arc::clone(&peer_finished),
        permits.try_acquire_owned().unwrap(),
    );

    blocked_entered.notified().await;
    assert_eq!(
        tokio::time::timeout(Duration::from_secs(1), blocked.cancel())
            .await
            .expect("blocked invocation was not hard-aborted"),
        CancelDisposition::Cancelled
    );
    tokio::time::timeout(Duration::from_secs(1), blocked_dropped.notified())
        .await
        .expect("blocked invocation state was not dropped");
    assert!(!peer_finished.load(Ordering::Acquire));

    peer_release.notify_one();
    tokio::time::timeout(Duration::from_secs(1), peer_done.notified())
        .await
        .expect("peer invocation was affected by cancellation");
    assert_eq!(peer.cancel().await, CancelDisposition::AlreadyFinished);
}
