mod callbacks;
mod projfs;
mod runtime;
mod winfsp;

use std::path::PathBuf;
use std::sync::Arc;

use anyhow::{Context, Result};

use crate::paths::is_literal_rule;
use crate::resident::ResidentWorkspace;
use crate::session;
use crate::store::Store;

enum Backend {
    WinFsp(winfsp::Provider),
    ProjFs(projfs::Provider),
}

pub struct Provider {
    backend: Backend,
    pub worktree: PathBuf,
}

impl Provider {
    pub fn start(
        store: &Store,
        session_id: &str,
        resident: Arc<ResidentWorkspace>,
    ) -> Result<Self> {
        let worktree = session::worktree(store, session_id)?;
        let has_native_scratch = store
            .scratch_paths(session_id)?
            .iter()
            .any(|path| is_literal_rule(path));
        let (backend, worktree) = if has_native_scratch {
            (
                Backend::ProjFs(projfs::Provider::start(store, session_id, resident)?),
                worktree,
            )
        } else {
            match winfsp::Provider::start(&worktree, Arc::clone(&resident)) {
                Ok(provider) => {
                    let mount_path = provider.worktree.clone();
                    (Backend::WinFsp(provider), mount_path)
                }
                Err(winfsp_error) => (
                    Backend::ProjFs(
                        projfs::Provider::start(store, session_id, resident).with_context(
                            || format!("WinFsp fast provider also failed: {winfsp_error:#}"),
                        )?,
                    ),
                    worktree,
                ),
            }
        };
        Ok(Self { backend, worktree })
    }

    pub fn backend_name(&self) -> &'static str {
        match self.backend {
            Backend::WinFsp(_) => "winfsp",
            Backend::ProjFs(_) => "projfs",
        }
    }

    pub fn unmount(&mut self) -> Result<()> {
        match &mut self.backend {
            Backend::WinFsp(provider) => provider.unmount(),
            Backend::ProjFs(provider) => provider.unmount(),
        }
    }

    pub fn is_mounted(&self) -> bool {
        match &self.backend {
            Backend::WinFsp(provider) => provider.is_mounted(),
            Backend::ProjFs(provider) => provider.is_mounted(),
        }
    }
}
