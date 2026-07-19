mod state;

use std::sync::Arc;

use reframe_store_protocol::wire::ProtocolVersion;

use crate::{LoadedStore, SessionOwner, invocation::ActiveInvocation};

pub(crate) use state::SessionState;

pub(crate) struct Session {
    pub(crate) id: String,
    pub(crate) owner: Option<SessionOwner>,
    pub(crate) protocol: ProtocolVersion,
    pub(crate) store: Arc<LoadedStore>,
    state: Arc<SessionState>,
}

impl Session {
    pub(crate) fn new(
        id: String,
        owner: Option<SessionOwner>,
        protocol: ProtocolVersion,
        store: Arc<LoadedStore>,
        completion_history: usize,
    ) -> Self {
        Self {
            id,
            owner,
            protocol,
            store,
            state: Arc::new(SessionState::new(completion_history)),
        }
    }

    pub(crate) fn state(&self) -> &Arc<SessionState> {
        &self.state
    }

    pub(crate) fn is_closed(&self) -> bool {
        self.state.is_closed()
    }

    pub(crate) fn close(&self) -> bool {
        self.state.close()
    }

    pub(crate) fn begin_request(&self, request_id: &str) -> bool {
        self.state.begin_request(request_id)
    }

    pub(crate) fn finish_request(&self, request_id: &str) {
        self.state.finish_request(request_id);
    }

    pub(crate) fn try_add_invocation(
        &self,
        request_id: String,
        invocation: Arc<ActiveInvocation>,
        maximum: usize,
    ) -> bool {
        self.state
            .try_add_invocation(request_id, invocation, maximum)
    }

    pub(crate) fn invocation(&self, request_id: &str) -> Option<Arc<ActiveInvocation>> {
        self.state.invocation(request_id)
    }

    pub(crate) fn invocation_ids(&self) -> Vec<String> {
        self.state.invocation_ids()
    }

    pub(crate) async fn was_completed(&self, request_id: &str) -> bool {
        self.state.was_completed(request_id).await
    }
}
