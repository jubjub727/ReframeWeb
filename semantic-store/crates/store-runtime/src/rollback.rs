pub(crate) struct Rollback<F: FnOnce()> {
    action: Option<F>,
}

impl<F: FnOnce()> Rollback<F> {
    pub(crate) fn new(action: F) -> Self {
        Self {
            action: Some(action),
        }
    }

    pub(crate) fn disarm(mut self) {
        self.action = None;
    }
}

impl<F: FnOnce()> Drop for Rollback<F> {
    fn drop(&mut self) {
        if let Some(action) = self.action.take() {
            action();
        }
    }
}

#[cfg(test)]
mod tests {
    use std::sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    };

    #[tokio::test]
    async fn cancellation_runs_the_armed_rollback() {
        let rolled_back = Arc::new(AtomicBool::new(false));
        let task_flag = Arc::clone(&rolled_back);
        let (armed, armed_rx) = tokio::sync::oneshot::channel();
        let task = tokio::spawn(async move {
            let _rollback = super::Rollback::new(move || {
                task_flag.store(true, Ordering::Release);
            });
            armed.send(()).expect("armed signal");
            std::future::pending::<()>().await;
        });

        armed_rx.await.expect("rollback armed");
        task.abort();
        assert!(task.await.unwrap_err().is_cancelled());
        assert!(rolled_back.load(Ordering::Acquire));
    }

    #[test]
    fn disarming_suppresses_the_rollback() {
        let rolled_back = Arc::new(AtomicBool::new(false));
        let flag = Arc::clone(&rolled_back);
        super::Rollback::new(move || flag.store(true, Ordering::Release)).disarm();
        assert!(!rolled_back.load(Ordering::Acquire));
    }
}
