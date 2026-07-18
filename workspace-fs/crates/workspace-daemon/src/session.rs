mod checkpoint;
mod create;
mod lifecycle;
mod scanning;
mod state;
mod worktree_guard;

#[cfg(test)]
mod tests;

pub use checkpoint::{checkpoint, checkpoint_resident};
#[cfg(test)]
pub use create::create;
pub(crate) use create::create_with_sources_cached;
pub use lifecycle::{apply_scratch_paths, close, destroy_ephemeral, status};
pub use state::{baseline, ensure_active, list, replace_journal, scratch_matcher, worktree};
