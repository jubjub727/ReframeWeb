use std::cell::RefCell;
use std::collections::HashMap;
use std::fs::{self, OpenOptions};
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::path::PathBuf;

use fuser::{Errno, INodeNo, OpenFlags};

use super::OpenFileTable;
use crate::unix_vfs::index::InodeTable;
use crate::unix_vfs::scratch::ScratchBackend;

const READ_WRITE: OpenFlags = OpenFlags(libc::O_RDWR);

#[test]
fn detached_resident_file_remains_shared_readable_writable_and_resizable() {
    let storage = RefCell::new(HashMap::from([("note.txt".to_owned(), b"before".to_vec())]));
    let mut table = OpenFileTable::new();
    let mut inodes = InodeTable::new();
    let (inode, _) = inodes.record_lookup("note.txt");
    let first_id = table.open_resident(inode, "note.txt", READ_WRITE).unwrap();
    let second_id = table.open_resident(inode, "note.txt", READ_WRITE).unwrap();
    let first = table.get(first_id, inode).unwrap();
    let second = table.get(second_id, inode).unwrap();

    table
        .unlink_resident(
            "note.txt",
            |path| Ok(storage.borrow().get(path).unwrap().clone()),
            || {
                storage.borrow_mut().remove("note.txt");
                Ok(())
            },
        )
        .unwrap();
    inodes.remove_path("note.txt");
    inodes.forget(inode, 1);
    assert!(inodes.path(inode).is_none());

    first
        .write(6, b"!", |_, _, _| -> Result<(), Errno> {
            panic!("detached writes must not recreate a path")
        })
        .unwrap();
    assert_eq!(
        second
            .read(0, 32, |_| -> Result<Vec<u8>, Errno> {
                panic!("detached reads must not resolve a path")
            })
            .unwrap(),
        b"before!"
    );
    second
        .resize(3, |_, _| -> Result<(), Errno> {
            panic!("detached resize must not recreate a path")
        })
        .unwrap();
    assert_eq!(first.len(|_| unreachable!()).unwrap(), 3);
    assert!(!storage.borrow().contains_key("note.txt"));
}

#[test]
fn overwrite_detaches_destination_while_source_handle_tracks_rename() {
    let storage = RefCell::new(HashMap::from([
        ("source.txt".to_owned(), b"source".to_vec()),
        ("destination.txt".to_owned(), b"destination".to_vec()),
    ]));
    let mut table = OpenFileTable::new();
    let source_inode = INodeNo(11);
    let destination_inode = INodeNo(12);
    let source_id = table
        .open_resident(source_inode, "source.txt", READ_WRITE)
        .unwrap();
    let destination_id = table
        .open_resident(destination_inode, "destination.txt", READ_WRITE)
        .unwrap();
    let source = table.get(source_id, source_inode).unwrap();
    let destination = table.get(destination_id, destination_inode).unwrap();

    table
        .rename_resident(
            "source.txt",
            "destination.txt",
            |path| Ok(storage.borrow().get(path).unwrap().clone()),
            || {
                let mut storage = storage.borrow_mut();
                let bytes = storage.remove("source.txt").unwrap();
                storage.insert("destination.txt".to_owned(), bytes);
                Ok(())
            },
        )
        .unwrap();

    assert_eq!(
        source
            .read(0, 32, |path| Ok(storage
                .borrow()
                .get(path)
                .unwrap()
                .clone()))
            .unwrap(),
        b"source"
    );
    source
        .write(6, b"!", |path, offset, data| {
            let mut storage = storage.borrow_mut();
            let bytes = storage.get_mut(path).unwrap();
            let offset = offset as usize;
            let end = offset + data.len();
            bytes.resize(bytes.len().max(end), 0);
            bytes[offset..end].copy_from_slice(data);
            Ok(())
        })
        .unwrap();
    assert_eq!(storage.borrow()["destination.txt"], b"source!");
    assert_eq!(
        destination
            .read(0, 32, |_| -> Result<Vec<u8>, Errno> { unreachable!() })
            .unwrap(),
        b"destination"
    );
}

#[test]
fn directory_rename_retargets_linked_descendant_handle() {
    let storage = RefCell::new(HashMap::from([(
        "old/nested/file.txt".to_owned(),
        b"nested".to_vec(),
    )]));
    let mut table = OpenFileTable::new();
    let inode = INodeNo(15);
    let handle_id = table
        .open_resident(inode, "old/nested/file.txt", READ_WRITE)
        .unwrap();
    let handle = table.get(handle_id, inode).unwrap();

    table
        .rename_resident(
            "old",
            "new",
            |path| Ok(storage.borrow().get(path).unwrap().clone()),
            || {
                let bytes = storage.borrow_mut().remove("old/nested/file.txt").unwrap();
                storage
                    .borrow_mut()
                    .insert("new/nested/file.txt".to_owned(), bytes);
                Ok(())
            },
        )
        .unwrap();

    assert_eq!(
        handle
            .read(0, 32, |path| {
                assert_eq!(path, "new/nested/file.txt");
                Ok(storage.borrow().get(path).unwrap().clone())
            })
            .unwrap(),
        b"nested"
    );
}

#[test]
fn failed_unlink_restores_the_resident_link() {
    let mut table = OpenFileTable::new();
    let inode = INodeNo(20);
    let handle_id = table.open_resident(inode, "kept.txt", READ_WRITE).unwrap();
    let handle = table.get(handle_id, inode).unwrap();

    let error = table
        .unlink_resident("kept.txt", |_| Ok(b"kept".to_vec()), || Err(Errno::EACCES))
        .unwrap_err();
    assert_eq!(error.code(), libc::EACCES);
    assert_eq!(
        handle
            .read(0, 8, |path| {
                assert_eq!(path, "kept.txt");
                Ok(b"kept".to_vec())
            })
            .unwrap(),
        b"kept"
    );
}

#[test]
fn release_removes_only_the_released_open_handle() {
    let mut table = OpenFileTable::new();
    let inode = INodeNo(30);
    let first = table
        .open_resident(inode, "shared.txt", READ_WRITE)
        .unwrap();
    let second = table
        .open_resident(inode, "shared.txt", READ_WRITE)
        .unwrap();

    table.release(first, inode).unwrap();
    assert!(table.get(first, inode).is_err());
    assert!(table.get(second, inode).is_ok());
    table.release(second, inode).unwrap();
    assert!(table.get(second, inode).is_err());
}

#[test]
fn indexed_unlink_does_not_lock_an_unrelated_poisoned_handle() {
    let mut table = OpenFileTable::new();
    let affected_inode = INodeNo(35);
    let unrelated_inode = INodeNo(36);
    table
        .open_resident(affected_inode, "target/file.txt", READ_WRITE)
        .unwrap();
    table
        .open_resident(unrelated_inode, "elsewhere/file.txt", READ_WRITE)
        .unwrap();
    let unrelated = table.resident_state(unrelated_inode);
    let _ = catch_unwind(AssertUnwindSafe(|| {
        let _guard = unrelated.lock().unwrap();
        panic!("poison unrelated resident state");
    }));

    table
        .unlink_resident("target", |_| Ok(b"target".to_vec()), || Ok(()))
        .unwrap();
}

#[test]
fn indexed_rename_does_not_lock_an_unrelated_poisoned_handle() {
    let mut table = OpenFileTable::new();
    let source_inode = INodeNo(37);
    let unrelated_inode = INodeNo(38);
    let source_handle = table
        .open_resident(source_inode, "source/file.txt", READ_WRITE)
        .unwrap();
    table
        .open_resident(unrelated_inode, "elsewhere/file.txt", READ_WRITE)
        .unwrap();
    let unrelated = table.resident_state(unrelated_inode);
    let _ = catch_unwind(AssertUnwindSafe(|| {
        let _guard = unrelated.lock().unwrap();
        panic!("poison unrelated resident state");
    }));

    table
        .rename_resident("source", "destination", |_| unreachable!(), || Ok(()))
        .unwrap();
    let source = table.get(source_handle, source_inode).unwrap();
    assert_eq!(
        source
            .read(0, 1, |path| {
                assert_eq!(path, "destination/file.txt");
                Ok(Vec::new())
            })
            .unwrap(),
        Vec::<u8>::new()
    );
}

#[test]
fn native_scratch_handle_survives_unlink_and_rename_overwrite() {
    let root = TempRoot::new("scratch-handles");
    let scratch = ScratchBackend::new(root.path.clone()).unwrap();
    let file = scratch.create_file("unlinked.txt", READ_WRITE).unwrap();
    let mut table = OpenFileTable::new();
    let inode = INodeNo(40);
    let handle_id = table.open_scratch(inode, file, READ_WRITE);
    let handle = table.get(handle_id, inode).unwrap();
    handle
        .write(0, b"scratch", |_, _, _| unreachable!())
        .unwrap();
    scratch.remove("unlinked.txt", false).unwrap();

    handle.write(7, b"!", |_, _, _| unreachable!()).unwrap();
    assert_eq!(handle.read(0, 32, |_| unreachable!()).unwrap(), b"scratch!");
    handle.resize(4, |_, _| unreachable!()).unwrap();
    assert_eq!(handle.read(0, 32, |_| unreachable!()).unwrap(), b"scra");

    let source = root.path.join("source.txt");
    let destination = root.path.join("destination.txt");
    fs::write(&source, b"new").unwrap();
    fs::write(&destination, b"old").unwrap();
    let destination_file = OpenOptions::new()
        .read(true)
        .write(true)
        .open(&destination)
        .unwrap();
    let overwritten = table.open_scratch(INodeNo(41), destination_file, READ_WRITE);
    let overwritten = table.get(overwritten, INodeNo(41)).unwrap();
    fs::rename(source, destination).unwrap();
    assert_eq!(overwritten.read(0, 32, |_| unreachable!()).unwrap(), b"old");
}

struct TempRoot {
    path: PathBuf,
}

impl TempRoot {
    fn new(label: &str) -> Self {
        let path = std::env::temp_dir().join(format!(
            "reframe-{label}-{}-{}",
            std::process::id(),
            uuid::Uuid::new_v4()
        ));
        fs::create_dir_all(&path).unwrap();
        Self { path }
    }
}

impl Drop for TempRoot {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.path);
    }
}
