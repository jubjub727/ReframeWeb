mod framing;
mod idempotency;
mod lifecycle;
mod operations;
mod server;
mod transport;

#[cfg(test)]
#[path = "daemon/cleanup_tests.rs"]
mod cleanup_tests;
#[cfg(test)]
#[path = "daemon/tests.rs"]
mod daemon_tests;
#[cfg(test)]
#[path = "daemon/protocol_tests.rs"]
mod protocol_tests;
#[cfg(test)]
#[path = "daemon/response_tests.rs"]
mod response_tests;
#[cfg(test)]
#[path = "daemon/source_tests.rs"]
mod source_tests;

use std::collections::HashMap;
use std::sync::Arc;

use crate::resident::{ContentCache, ResidentWorkspace};
use crate::store::Store;

#[cfg(unix)]
use crate::unix_vfs::Provider;
#[cfg(windows)]
use crate::windows_vfs::Provider;

pub use transport::{serve, serve_socket};

struct Daemon {
    store: Store,
    content_cache: ContentCache,
    residents: HashMap<String, Arc<ResidentWorkspace>>,
    process_idempotency_requests: idempotency::ProcessIdempotencyRequests,
    #[cfg(any(windows, unix))]
    mounts: HashMap<String, Provider>,
    #[cfg(not(any(windows, unix)))]
    mounts: HashMap<String, ()>,
}
