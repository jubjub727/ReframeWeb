use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};

pub(super) struct WorktreeGuard {
    session_root: PathBuf,
    armed: bool,
}

impl WorktreeGuard {
    pub(super) fn create(session_root: &Path, worktree: &Path) -> Result<Self> {
        let guard = Self {
            session_root: session_root.to_path_buf(),
            armed: true,
        };
        if let Err(error) = fs::create_dir_all(worktree)
            .with_context(|| format!("create session worktree {}", worktree.display()))
        {
            return match guard.cleanup() {
                Ok(()) => Err(error),
                Err(cleanup_error) => Err(error.context(format!(
                    "partial worktree cleanup also failed: {cleanup_error:#}"
                ))),
            };
        }
        Ok(guard)
    }

    pub(super) fn cleanup(mut self) -> Result<()> {
        self.armed = false;
        remove_session_root(&self.session_root)
    }

    pub(super) fn disarm(mut self) {
        self.armed = false;
    }
}

impl Drop for WorktreeGuard {
    fn drop(&mut self) {
        if self.armed {
            if let Err(error) = remove_session_root(&self.session_root) {
                eprintln!("[workspace-daemon] failed to roll back session worktree: {error:#}");
            }
        }
    }
}

fn remove_session_root(session_root: &Path) -> Result<()> {
    match fs::remove_dir_all(session_root) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error)
            .with_context(|| format!("remove session directory {}", session_root.display())),
    }
}

#[cfg(test)]
#[path = "worktree_guard/tests.rs"]
mod tests;
