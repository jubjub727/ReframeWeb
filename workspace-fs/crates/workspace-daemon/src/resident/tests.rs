use std::sync::Arc;

use anyhow::Result;

use crate::model::ChangeKind;
use crate::paths::ScratchMatcher;

use super::{ResidentFile, ResidentState, ResidentWorkspace};

fn empty_workspace() -> ResidentWorkspace {
    ResidentWorkspace {
        state: std::sync::RwLock::new(ResidentState::default()),
        scratch: ScratchMatcher::compile(std::iter::empty::<&str>()).unwrap(),
    }
}

#[test]
fn resident_writes_are_sparse_and_reported() -> Result<()> {
    let workspace = empty_workspace();
    workspace.write("notes/result.txt", 3, b"ok")?;
    assert_eq!(
        &*workspace.file("notes/result.txt").unwrap().bytes,
        b"\0\0\0ok"
    );
    assert!(
        workspace
            .changes()
            .iter()
            .any(|change| change.path == "notes/result.txt" && change.kind == ChangeKind::Create)
    );
    Ok(())
}

#[test]
fn duplicate_content_shares_one_allocation() {
    let bytes: Arc<[u8]> = Vec::from("shared").into();
    let left = ResidentFile {
        bytes: Arc::clone(&bytes),
        hash: "hash".into(),
    };
    let right = ResidentFile {
        bytes: Arc::clone(&bytes),
        hash: "hash".into(),
    };
    assert!(Arc::ptr_eq(&left.bytes, &right.bytes));
}

#[test]
fn empty_directories_are_resident_and_checkpointable() -> Result<()> {
    let workspace = empty_workspace();
    workspace.create_directory("empty/nested")?;
    assert!(workspace.is_directory("empty/nested"));
    assert_eq!(workspace.changes().len(), 2);
    workspace.mark_checkpointed(&["empty".into(), "empty/nested".into()])?;
    assert!(workspace.changes().is_empty());
    Ok(())
}

#[test]
fn removing_a_new_file_cancels_its_journal_entry() -> Result<()> {
    let workspace = empty_workspace();
    workspace.replace("draft.txt", b"draft".to_vec())?;
    workspace.remove("draft.txt")?;
    assert!(workspace.changes().is_empty());
    Ok(())
}
