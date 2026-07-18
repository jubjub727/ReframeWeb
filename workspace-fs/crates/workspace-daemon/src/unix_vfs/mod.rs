mod callbacks;
mod error;
mod filesystem;
mod handles;
mod index;
mod scratch;
mod unmount;

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

    pub fn unmount(&mut self) -> Result<()> {
        if let Some(session) = self.session.as_ref() {
            let session_finished = session.guard.is_finished();
            if let Err(error) = unmount::unmount_path(&self.worktree) {
                if !(session_finished && unmount::is_already_unmounted(&error)) {
                    return Err(error).with_context(|| {
                        format!("unmount workspace at {}", self.worktree.display())
                    });
                }
            }
        }
        if let Some(session) = self.session.take() {
            if let Err(error) = session.join() {
                eprintln!(
                    "workspace-fs session join failed after unmounting {}: {error}",
                    self.worktree.display()
                );
            }
        }
        self.remove_scratch()
    }

    pub fn is_mounted(&self) -> bool {
        self.session
            .as_ref()
            .is_some_and(|session| !session.guard.is_finished())
    }

    pub fn backend_name(&self) -> &'static str {
        "fuse"
    }

    fn remove_scratch(&self) -> Result<()> {
        if self.scratch_root.exists() {
            std::fs::remove_dir_all(&self.scratch_root).with_context(|| {
                format!("remove scratch directory {}", self.scratch_root.display())
            })?;
        }
        Ok(())
    }
}

impl Drop for Provider {
    fn drop(&mut self) {
        drop(self.session.take());
        if let Err(error) = self.remove_scratch() {
            eprintln!("workspace-fs cleanup failed: {error:#}");
        }
    }
}
