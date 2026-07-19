use std::sync::atomic::{AtomicU64, Ordering};

static NEXT_CONNECTION_ID: AtomicU64 = AtomicU64::new(1);

/// Process-local identity for one accepted transport connection.
#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct ConnectionId(u64);

impl ConnectionId {
    pub(super) fn next() -> Self {
        let id = NEXT_CONNECTION_ID
            .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |current| {
                current.checked_add(1)
            })
            .expect("process exhausted every Semantic Store connection ID");
        Self(id)
    }

    #[must_use]
    pub const fn get(self) -> u64 {
        self.0
    }
}
