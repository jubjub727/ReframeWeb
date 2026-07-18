mod filesystem;
mod index;
mod scratch;

use std::path::PathBuf;
use std::sync::Arc;

use anyhow::{Context, Result};
use fuser::{BackgroundSession, Config, MountOption};

use crate::resident::ResidentWorkspace;
use crate::session;
use crate::store::Store;
use filesystem::ResidentFuse;

pub struct Provider {
    session: Option<BackgroundSession>,
    scratch_root: PathBuf,
    pub worktree: PathBuf,
}

impl Provider {
    pub fn start(
        store: &Store,
        session_id: &str,
        resident: Arc<ResidentWorkspace>,
    ) -> Result<Self> {
        let worktree = session::worktree(store, session_id)?;
        let scratch_root = worktree
            .parent()
            .context("session worktree has no parent")?
            .join("scratch");
        let mut config = Config::default();
        config.mount_options = vec![
            MountOption::FSName(format!("reframe-{session_id}")),
            MountOption::Subtype("reframe-workspace".into()),
            MountOption::RW,
            MountOption::NoAtime,
            MountOption::NoDev,
            MountOption::NoSuid,
            MountOption::DefaultPermissions,
        ];
        config.n_threads = std::thread::available_parallelism().ok().map(usize::from);
        let filesystem = ResidentFuse::new(resident, scratch_root)?;
        let session = fuser::spawn_mount2(filesystem, &worktree, &config)
            .with_context(|| format!("mount resident workspace at {}", worktree.display()))?;
        Ok(Self {
            session: Some(session),
            scratch_root,
            worktree,
        })
    }
}

impl Drop for Provider {
    fn drop(&mut self) {
        drop(self.session.take());
        if self.scratch_root.exists() {
            let _ = std::fs::remove_dir_all(&self.scratch_root);
        }
    }
}
