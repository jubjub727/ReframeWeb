use std::{
    collections::{HashSet, VecDeque},
    sync::{
        Arc,
        atomic::{AtomicBool, AtomicUsize, Ordering},
    },
};

use dashmap::{DashMap, mapref::entry::Entry};
use tokio::sync::Mutex;

use crate::invocation::ActiveInvocation;

pub(crate) struct SessionState {
    closed: AtomicBool,
    lifecycle: std::sync::Mutex<()>,
    requests: DashMap<String, ()>,
    invocations: DashMap<String, Arc<ActiveInvocation>>,
    completed: Mutex<CompletionHistory>,
    active_invocations: AtomicUsize,
}

impl SessionState {
    pub(crate) fn new(completion_history: usize) -> Self {
        Self {
            closed: AtomicBool::new(false),
            lifecycle: std::sync::Mutex::new(()),
            requests: DashMap::new(),
            invocations: DashMap::new(),
            completed: Mutex::new(CompletionHistory::new(completion_history)),
            active_invocations: AtomicUsize::new(0),
        }
    }

    pub(crate) fn is_closed(&self) -> bool {
        self.closed.load(Ordering::Acquire)
    }

    pub(crate) fn close(&self) -> bool {
        let _lifecycle = self
            .lifecycle
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        !self.closed.swap(true, Ordering::AcqRel)
    }

    pub(crate) fn begin_request(&self, request_id: &str) -> bool {
        let _lifecycle = self
            .lifecycle
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        !self.is_closed() && self.requests.insert(request_id.to_owned(), ()).is_none()
    }

    pub(crate) fn finish_request(&self, request_id: &str) {
        self.requests.remove(request_id);
    }

    pub(crate) fn try_add_invocation(
        &self,
        request_id: String,
        invocation: Arc<ActiveInvocation>,
        maximum: usize,
    ) -> bool {
        let _lifecycle = self
            .lifecycle
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let reserved = self
            .active_invocations
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |active| {
                (active < maximum).then_some(active + 1)
            })
            .is_ok();
        if !reserved {
            return false;
        }

        if self.is_closed() {
            self.active_invocations.fetch_sub(1, Ordering::AcqRel);
            return false;
        }
        match self.invocations.entry(request_id) {
            Entry::Vacant(entry) => {
                entry.insert(invocation);
            }
            Entry::Occupied(_) => {
                self.active_invocations.fetch_sub(1, Ordering::AcqRel);
                return false;
            }
        }
        true
    }

    pub(crate) fn invocation(&self, request_id: &str) -> Option<Arc<ActiveInvocation>> {
        self.invocations
            .get(request_id)
            .map(|entry| Arc::clone(entry.value()))
    }

    pub(crate) fn invocation_ids(&self) -> Vec<String> {
        self.invocations
            .iter()
            .map(|entry| entry.key().clone())
            .collect()
    }

    pub(crate) async fn finish_invocation(&self, request_id: &str) {
        self.finish_request(request_id);
        self.completed.lock().await.insert(request_id.to_owned());
        if self.invocations.remove(request_id).is_some() {
            self.active_invocations.fetch_sub(1, Ordering::AcqRel);
        }
    }

    pub(crate) async fn was_completed(&self, request_id: &str) -> bool {
        self.completed.lock().await.contains(request_id)
    }

    #[cfg(test)]
    pub(crate) fn active_invocation_count(&self) -> usize {
        self.active_invocations.load(Ordering::Acquire)
    }
}

struct CompletionHistory {
    capacity: usize,
    order: VecDeque<String>,
    values: HashSet<String>,
}

impl CompletionHistory {
    fn new(capacity: usize) -> Self {
        Self {
            capacity,
            order: VecDeque::new(),
            values: HashSet::new(),
        }
    }

    fn insert(&mut self, request_id: String) {
        if !self.values.insert(request_id.clone()) {
            return;
        }
        self.order.push_back(request_id);
        if self.order.len() > self.capacity
            && let Some(expired) = self.order.pop_front()
        {
            self.values.remove(&expired);
        }
    }

    fn contains(&self, request_id: &str) -> bool {
        self.values.contains(request_id)
    }
}
