use std::sync::Arc;

use anyhow::Result;

use crate::model::ChangeKind;
use crate::paths::ScratchMatcher;

use super::{ResidentFile, ResidentState, ResidentWorkspace};

fn empty_workspace() -> ResidentWorkspace {
    ResidentWorkspace {
        state: std::sync::RwLock::new(ResidentState::default()),
        scratch: ScratchMatcher::compile(std::iter::empty::<&str>()).unwrap(),
        file_count: std::sync::atomic::AtomicUsize::new(0),
        byte_count: std::sync::atomic::AtomicU64::new(0),
    }
}

#[test]
fn resident_writes_are_sparse_and_reported() -> Result<()> {
    let workspace = empty_workspace();
    workspace.write("notes/result.txt", 3, b"ok")?;
    assert_eq!(
        &*workspace.file("notes/result.txt").unwrap().snapshot()?,
        b"\0\0\0ok"
    );
    assert!(
        workspace
            .changes()?
            .iter()
            .any(|change| change.path == "notes/result.txt" && change.kind == ChangeKind::Create)
    );
    Ok(())
}

#[test]
fn duplicate_content_shares_one_allocation() {
    let bytes: Arc<[u8]> = Vec::from("shared").into();
    let blob = crate::store::VerifiedBlob::new(Arc::clone(&bytes));
    let left = ResidentFile::shared(blob.clone());
    let right = ResidentFile::shared(blob);
    assert!(Arc::ptr_eq(
        &left.snapshot().unwrap(),
        &right.snapshot().unwrap()
    ));
}

#[test]
fn first_small_edit_of_a_shared_file_copies_only_touched_pages() -> Result<()> {
    let bytes: Arc<[u8]> = vec![b'a'; 16 * 1024 * 1024].into();
    let file = ResidentFile::shared(crate::store::VerifiedBlob::new(bytes));

    file.write(7 * 4096 + 13, b"changed")?;

    assert_eq!(file.storage_metrics(), ("overlay", 4096));
    assert_eq!(file.read_range(7 * 4096 + 13, 7)?, b"changed");
    Ok(())
}

#[test]
fn hashing_between_shared_file_edits_does_not_rearm_full_file_copy() -> Result<()> {
    let bytes: Arc<[u8]> = vec![b'a'; 8 * 1024 * 1024].into();
    let file = ResidentFile::shared(crate::store::VerifiedBlob::new(bytes));
    file.write(17, b"first")?;

    let first_hash = file.hash_hex()?;
    assert_eq!(file.storage_metrics(), ("overlay", 4096));
    file.write(5 * 4096 + 19, b"second")?;

    assert_eq!(file.storage_metrics(), ("overlay", 2 * 4096));
    assert_ne!(file.hash_hex()?, first_hash);
    assert_eq!(file.storage_metrics(), ("overlay", 2 * 4096));
    Ok(())
}

#[test]
fn truncating_shared_content_does_not_materialize_it() -> Result<()> {
    let bytes: Arc<[u8]> = vec![b'a'; 16 * 1024 * 1024].into();
    let file = ResidentFile::shared(crate::store::VerifiedBlob::new(bytes));

    file.resize(0)?;

    assert_eq!(file.storage_metrics(), ("owned", 0));
    assert_eq!(file.len(), 0);
    Ok(())
}

#[test]
fn truncated_shared_bytes_stay_zero_after_extension() -> Result<()> {
    let bytes: Arc<[u8]> = Vec::from(&b"original"[..]).into();
    let file = ResidentFile::shared(crate::store::VerifiedBlob::new(bytes));

    file.resize(3)?;
    file.resize(8)?;

    assert_eq!(file.read_range(0, 8)?, b"ori\0\0\0\0\0");
    Ok(())
}

#[test]
fn paged_edits_preserve_holes_and_cross_page_writes() -> Result<()> {
    let bytes: Arc<[u8]> = vec![b'b'; 2 * 4096].into();
    let file = ResidentFile::shared(crate::store::VerifiedBlob::new(bytes));

    file.write(4093, b"cross-page")?;
    file.write(3 * 4096 + 9, b"tail")?;

    assert_eq!(file.read_range(4090, 16)?, b"bbbcross-pagebbb");
    assert!(
        file.read_range(2 * 4096, 4096 + 9)?
            .iter()
            .all(|byte| *byte == 0)
    );
    assert_eq!(file.read_range(3 * 4096 + 9, 4)?, b"tail");
    Ok(())
}

#[test]
fn empty_directories_are_resident_and_checkpointable() -> Result<()> {
    let workspace = empty_workspace();
    workspace.create_directory("empty/nested")?;
    assert!(workspace.is_directory("empty/nested"));
    assert_eq!(workspace.changes()?.len(), 2);
    workspace.mark_checkpointed(&["empty".into(), "empty/nested".into()])?;
    assert!(workspace.changes()?.is_empty());
    Ok(())
}

#[test]
fn removing_a_new_file_cancels_its_journal_entry() -> Result<()> {
    let workspace = empty_workspace();
    workspace.replace("draft.txt", b"draft".to_vec())?;
    workspace.remove("draft.txt")?;
    assert!(workspace.changes()?.is_empty());
    assert!(workspace.state.read().unwrap().dirty.is_empty());
    Ok(())
}

#[test]
fn lazy_hashing_drops_an_edit_that_returns_to_the_checkpoint() -> Result<()> {
    let workspace = empty_workspace();
    workspace.replace("note.txt", b"baseline".to_vec())?;
    workspace.mark_checkpointed(&["note.txt".into()])?;

    workspace.write("note.txt", 0, b"changed!")?;
    assert_eq!(workspace.changes()?.len(), 1);
    workspace.replace("note.txt", b"baseline".to_vec())?;

    assert!(workspace.changes()?.is_empty());
    assert!(workspace.state.read().unwrap().dirty.is_empty());

    workspace.write("note.txt", 0, b"changed!")?;
    assert_eq!(workspace.changes()?.len(), 1);
    Ok(())
}

#[test]
fn canceled_changes_do_not_accumulate_dirty_history() -> Result<()> {
    let workspace = empty_workspace();

    for index in 0..2_048 {
        let path = format!("temporary-{index}.txt");
        workspace.replace(&path, b"temporary".to_vec())?;
        workspace.remove(&path)?;
        assert!(workspace.state.read().unwrap().dirty.is_empty());
        assert!(workspace.changes()?.is_empty());
    }

    assert!(workspace.state.read().unwrap().dirty.is_empty());
    Ok(())
}

#[test]
fn single_file_rename_updates_stats_and_both_directory_indexes() -> Result<()> {
    let workspace = empty_workspace();
    workspace.replace("source/note.txt", b"longer source".to_vec())?;
    workspace.replace("destination/note.txt", b"old".to_vec())?;

    workspace.rename("source/note.txt", "destination/note.txt")?;

    assert!(workspace.entries("source").is_empty());
    assert_eq!(
        workspace.entries("destination"),
        vec![("note.txt".into(), false, 13)]
    );
    assert_eq!(workspace.stats().files, 1);
    assert_eq!(workspace.stats().bytes, 13);
    assert_eq!(
        workspace
            .file("destination/note.txt")
            .expect("renamed file")
            .snapshot()?
            .as_ref(),
        b"longer source"
    );
    Ok(())
}

#[test]
fn rejected_replacement_renames_preserve_both_trees() -> Result<()> {
    let workspace = empty_workspace();
    workspace.replace("file-source", b"source".to_vec())?;
    workspace.create_directory("directory-destination/nested")?;
    assert!(
        workspace
            .rename_with_replace("file-source", "directory-destination", true)
            .err()
            .expect("file-over-directory rename must fail")
            .to_string()
            .contains("file over a directory")
    );
    assert!(workspace.contains_file("file-source"));
    assert!(workspace.is_directory("directory-destination/nested"));

    workspace.create_directory("directory-source")?;
    workspace.replace("file-destination", b"destination".to_vec())?;
    assert!(
        workspace
            .rename_with_replace("directory-source", "file-destination", true)
            .err()
            .expect("directory-over-file rename must fail")
            .to_string()
            .contains("directory over a file")
    );
    assert!(workspace.is_directory("directory-source"));
    assert_eq!(
        workspace
            .file("file-destination")
            .expect("destination file")
            .snapshot()?
            .as_ref(),
        b"destination"
    );

    workspace.replace("collision-source", b"left".to_vec())?;
    workspace.replace("collision-destination", b"right".to_vec())?;
    assert!(
        workspace
            .rename_with_replace("collision-source", "collision-destination", false)
            .err()
            .expect("non-replacing rename must fail")
            .to_string()
            .contains("destination already exists")
    );
    assert!(workspace.contains_file("collision-source"));
    assert_eq!(
        workspace
            .file("collision-destination")
            .expect("collision destination")
            .snapshot()?
            .as_ref(),
        b"right"
    );
    Ok(())
}

#[test]
fn indexed_directory_pagination_visits_linear_entries() -> Result<()> {
    const ENTRY_COUNT: usize = 10_000;
    const PAGE_SIZE: usize = 31;

    let workspace = empty_workspace();
    for index in 0..ENTRY_COUNT {
        workspace.replace(&format!("huge/{index:05}.md"), Vec::new())?;
    }

    let mut marker: Option<String> = None;
    let mut observed = Vec::with_capacity(ENTRY_COUNT);
    let mut visits = 0usize;
    loop {
        let mut page = Vec::with_capacity(PAGE_SIZE);
        let complete = workspace.visit_entries_after(
            "huge",
            marker.as_deref(),
            |name, _directory, _size| {
                visits += 1;
                if page.len() == PAGE_SIZE {
                    return false;
                }
                page.push(name.to_owned());
                true
            },
        )?;
        observed.extend(page.iter().cloned());
        marker = page.last().cloned();
        if complete {
            break;
        }
    }

    assert_eq!(observed.len(), ENTRY_COUNT);
    assert!(observed.windows(2).all(|pair| pair[0] < pair[1]));
    let maximum_visits = ENTRY_COUNT + ENTRY_COUNT.div_ceil(PAGE_SIZE);
    assert!(visits <= maximum_visits, "visited {visits} entries");
    Ok(())
}
