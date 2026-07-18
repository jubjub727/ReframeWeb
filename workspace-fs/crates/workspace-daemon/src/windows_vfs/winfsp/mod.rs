mod callbacks;
mod host;
mod info;
mod path;
mod runtime;
mod security;
mod status;
mod version;

use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::Result;

use crate::resident::ResidentWorkspace;

pub(super) struct Provider {
    host: host::Host,
    pub(super) worktree: PathBuf,
}

impl Provider {
    pub(super) fn start(worktree: &Path, resident: Arc<ResidentWorkspace>) -> Result<Self> {
        let host = host::Host::start(worktree, resident)?;
        let worktree = host.mount_path().to_owned();
        Ok(Self { host, worktree })
    }

    pub(super) fn unmount(&mut self) -> Result<()> {
        self.host.stop();
        Ok(())
    }

    pub(super) fn is_mounted(&self) -> bool {
        self.host.is_running()
    }
}
