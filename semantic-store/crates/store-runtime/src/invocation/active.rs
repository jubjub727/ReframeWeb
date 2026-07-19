use std::sync::{
    Arc,
    atomic::{AtomicBool, Ordering},
};

use tokio::{
    sync::{Mutex, OwnedSemaphorePermit},
    task::JoinHandle,
};

use super::InvocationOutput;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum CancelDisposition {
    Cancelled,
    AlreadyFinished,
}

pub(crate) struct ActiveInvocation {
    cancel_gate: Mutex<()>,
    cancellation_started: AtomicBool,
    finished: Arc<AtomicBool>,
    output: Arc<Mutex<InvocationOutput>>,
    _permit: OwnedSemaphorePermit,
    task: Mutex<Option<JoinHandle<()>>>,
}

impl ActiveInvocation {
    pub(crate) fn new(
        output: Arc<Mutex<InvocationOutput>>,
        task: JoinHandle<()>,
        finished: Arc<AtomicBool>,
        permit: OwnedSemaphorePermit,
    ) -> Self {
        Self {
            cancel_gate: Mutex::new(()),
            cancellation_started: AtomicBool::new(false),
            finished,
            output,
            _permit: permit,
            task: Mutex::new(Some(task)),
        }
    }

    pub(crate) async fn cancel(&self) -> CancelDisposition {
        let _gate = self.cancel_gate.lock().await;
        if self.finished.load(Ordering::Acquire)
            || self.cancellation_started.load(Ordering::Acquire)
        {
            self.reap_finished_task().await;
            return CancelDisposition::AlreadyFinished;
        }

        if let Some(task) = self.task.lock().await.take() {
            task.abort();
            let _ = task.await;
        }

        if self.finished.load(Ordering::Acquire) {
            return CancelDisposition::AlreadyFinished;
        }
        self.cancellation_started.store(true, Ordering::Release);
        let output = Arc::clone(&self.output);
        drop(tokio::spawn(async move {
            if let Err(error) = output.lock().await.cancel().await {
                tracing::debug!(%error, "cancelled invocation response could not be delivered");
            }
        }));
        CancelDisposition::Cancelled
    }

    async fn reap_finished_task(&self) {
        let task = self.task.lock().await.take();
        if let Some(task) = task {
            let _ = task.await;
        }
    }

    pub(crate) async fn abort_silent(&self) {
        if let Some(task) = self.task.lock().await.take() {
            task.abort();
            let _ = task.await;
        }
    }
}

impl Drop for ActiveInvocation {
    fn drop(&mut self) {
        if !self.finished.load(Ordering::Acquire)
            && let Ok(mut task) = self.task.try_lock()
            && let Some(task) = task.take()
        {
            task.abort();
        }
    }
}

#[cfg(test)]
mod tests {
    use std::{
        sync::{
            Arc,
            atomic::{AtomicBool, Ordering},
        },
        time::Duration,
    };

    use async_trait::async_trait;
    use reframe_store_protocol::wire::Envelope;
    use reframe_store_protocol::{CURRENT_PROTOCOL_VERSION, wire::invocation_event};
    use tokio::sync::{Mutex, Notify, mpsc};

    use crate::{ChannelSink, InvocationMode, ResponseSink, ResponseSinkError};

    use super::*;

    #[tokio::test]
    async fn cancellation_before_guest_start_is_a_complete_ordered_stream() {
        let request_id = uuid::Uuid::new_v4().to_string();
        let session_id = uuid::Uuid::new_v4().to_string();
        let (sender, mut receiver) = mpsc::channel(4);
        let sink = Arc::new(ChannelSink::new(sender));
        let finished = Arc::new(AtomicBool::new(false));
        let output = Arc::new(Mutex::new(InvocationOutput::new(
            request_id.clone(),
            session_id,
            CURRENT_PROTOCOL_VERSION,
            InvocationMode::Subscription,
            sink,
            Duration::from_secs(1),
            Arc::clone(&finished),
        )));
        let task = tokio::spawn(std::future::pending());
        let permit = Arc::new(tokio::sync::Semaphore::new(1))
            .try_acquire_owned()
            .unwrap();
        let active = ActiveInvocation::new(output, task, finished, permit);

        assert_eq!(active.cancel().await, CancelDisposition::Cancelled);
        let started = receiver.recv().await.unwrap();
        let failed = receiver.recv().await.unwrap();
        assert_eq!(started.sequence_number, 0);
        assert_eq!(failed.sequence_number, 1);
        assert!(matches!(
            started.message,
            Some(reframe_store_protocol::wire::envelope::Message::InvocationEvent(event))
                if event.request_id == request_id
                    && matches!(event.event, Some(invocation_event::Event::Started(_)))
        ));
        assert!(matches!(
            failed.message,
            Some(reframe_store_protocol::wire::envelope::Message::InvocationEvent(event))
                if matches!(event.event, Some(invocation_event::Event::Failure(_)))
        ));
        assert_eq!(active.cancel().await, CancelDisposition::AlreadyFinished);
    }

    struct BlockingSink {
        entered: Arc<Notify>,
    }

    #[async_trait]
    impl ResponseSink for BlockingSink {
        async fn send(&self, _envelope: Envelope) -> Result<(), ResponseSinkError> {
            self.entered.notify_one();
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
    async fn hard_cancel_aborts_guest_before_blocked_response_timeout() {
        let entered = Arc::new(Notify::new());
        let dropped = Arc::new(Notify::new());
        let finished = Arc::new(AtomicBool::new(false));
        let sink: Arc<dyn ResponseSink> = Arc::new(BlockingSink {
            entered: Arc::clone(&entered),
        });
        let output = Arc::new(Mutex::new(InvocationOutput::new(
            uuid::Uuid::new_v4().to_string(),
            uuid::Uuid::new_v4().to_string(),
            CURRENT_PROTOCOL_VERSION,
            InvocationMode::Unary,
            sink,
            Duration::from_millis(200),
            Arc::clone(&finished),
        )));
        let task_output = Arc::clone(&output);
        let drop_notice = DropNotice(Arc::clone(&dropped));
        let task = tokio::spawn(async move {
            let _drop_notice = drop_notice;
            let _ = task_output
                .lock()
                .await
                .fail(reframe_store_protocol::wire::FailureCode::Internal, "test")
                .await;
        });
        entered.notified().await;
        let permit = Arc::new(tokio::sync::Semaphore::new(1))
            .try_acquire_owned()
            .unwrap();
        let active = Arc::new(ActiveInvocation::new(output, task, finished, permit));
        let cancelling = tokio::spawn({
            let active = Arc::clone(&active);
            async move { active.cancel().await }
        });

        tokio::time::timeout(Duration::from_millis(50), dropped.notified())
            .await
            .expect("guest task must be aborted before sink timeout");
        assert!(!active.finished.load(Ordering::Acquire));
        assert_eq!(
            tokio::time::timeout(Duration::from_secs(1), cancelling)
                .await
                .unwrap()
                .unwrap(),
            CancelDisposition::Cancelled
        );
    }
}
