use std::cell::Cell;
use std::panic::{AssertUnwindSafe, catch_unwind};

use fuser::{Errno, FileType, OpenFlags};

use super::mutation::{validate_rename, validate_rename_target, validate_subtree_storage};
use super::namespace::register_resident_create;
use crate::unix_vfs::filesystem::PathMetadata;
use crate::unix_vfs::handles::OpenFileTable;
use crate::unix_vfs::index::InodeTable;

fn metadata(kind: FileType) -> PathMetadata {
    PathMetadata {
        kind,
        size: 0,
        perm: 0,
    }
}

#[test]
fn rename_rejects_incompatible_kinds_and_non_empty_directory() {
    let cases = [
        (
            FileType::RegularFile,
            Some(metadata(FileType::Directory)),
            true,
            libc::EISDIR,
        ),
        (
            FileType::Directory,
            Some(metadata(FileType::RegularFile)),
            true,
            libc::ENOTDIR,
        ),
        (
            FileType::Directory,
            Some(metadata(FileType::Directory)),
            false,
            libc::ENOTEMPTY,
        ),
    ];
    for (source, destination, empty, expected) in cases {
        assert_eq!(
            validate_rename(source, destination, empty)
                .unwrap_err()
                .code(),
            expected
        );
    }
    assert!(
        validate_rename(
            FileType::Directory,
            Some(metadata(FileType::Directory)),
            true,
        )
        .is_ok()
    );
}

#[test]
fn rename_rejects_a_destination_inside_the_source() {
    assert_eq!(
        validate_rename_target("source", "source/nested")
            .unwrap_err()
            .code(),
        libc::EINVAL
    );
    assert!(validate_rename_target("source", "source-other").is_ok());
}

#[test]
fn rename_rejects_a_directory_with_mixed_backend_descendants() {
    let resident_paths = vec!["tree/file.txt".to_owned()];
    let scratch_paths = vec!["tree/.git".to_owned()];

    let error = validate_subtree_storage(
        "tree",
        "renamed",
        false,
        &resident_paths,
        &scratch_paths,
        |path| path.ends_with("/.git"),
    )
    .unwrap_err();

    assert_eq!(error.code(), libc::EXDEV);
}

#[test]
fn rename_rejects_descendants_that_change_backend_at_the_destination() {
    let resident_paths = vec!["tree/file.txt".to_owned()];

    let error =
        validate_subtree_storage("tree", "generated", false, &resident_paths, &[], |path| {
            path.starts_with("generated/")
        })
        .unwrap_err();

    assert_eq!(error.code(), libc::EXDEV);
}

#[test]
fn failed_resident_registration_rolls_back_backend_creation() {
    let mut handles = OpenFileTable::new();
    let mut inodes = InodeTable::new();
    let path = "failed.txt";
    let inode = inodes.ensure(path);
    handles
        .open_resident(inode, path, OpenFlags(libc::O_RDWR))
        .unwrap();
    let state = handles.resident_state(inode);
    let _ = catch_unwind(AssertUnwindSafe(|| {
        let _guard = state.lock().unwrap();
        panic!("poison resident state");
    }));
    let backend_exists = Cell::new(false);

    let error = register_resident_create(
        &mut handles,
        &mut inodes,
        path,
        OpenFlags(libc::O_RDWR),
        || {
            backend_exists.set(true);
            Ok(())
        },
        |handles, inode, path, flags| handles.open_resident(inode, path, flags),
        || {
            backend_exists.set(false);
            Ok(())
        },
    )
    .unwrap_err();

    assert_eq!(error.code(), libc::EIO);
    assert!(!backend_exists.get());
    assert_eq!(inodes.path(inode).as_deref(), Some(path));
}

#[test]
fn injected_create_failure_leaves_no_backend_inode_or_handle() {
    let mut handles = OpenFileTable::new();
    let mut inodes = InodeTable::new();
    let backend_exists = Cell::new(false);

    let error = register_resident_create(
        &mut handles,
        &mut inodes,
        "new.txt",
        OpenFlags(libc::O_RDWR),
        || {
            backend_exists.set(true);
            Ok(())
        },
        |_, _, _, _| Err(Errno::EIO),
        || {
            backend_exists.set(false);
            Ok(())
        },
    )
    .unwrap_err();

    assert_eq!(error.code(), libc::EIO);
    assert!(!backend_exists.get());
    assert!(inodes.inode_for_path("new.txt").is_none());
    assert_eq!(handles.handle_count(), 0);
}
