use std::fs;

use anyhow::Result;

use super::WorktreeGuard;

#[test]
fn armed_guard_removes_the_session_tree() -> Result<()> {
    let root =
        std::env::temp_dir().join(format!("reframe-worktree-guard-{}", uuid::Uuid::new_v4()));
    let worktree = root.join("worktree");
    let guard = WorktreeGuard::create(&root, &worktree)?;
    fs::write(worktree.join("partial"), b"partial")?;
    drop(guard);
    assert!(!root.exists());
    Ok(())
}
