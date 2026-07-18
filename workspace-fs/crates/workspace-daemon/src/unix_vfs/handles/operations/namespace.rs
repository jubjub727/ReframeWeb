use std::ffi::OsStr;

use fuser::{Errno, FileAttr, FileHandle, FileType, Generation, INodeNo, OpenFlags};

use super::{DirectoryEntry, child_path};
use crate::unix_vfs::error::errno;
use crate::unix_vfs::filesystem::ResidentFuse;
use crate::unix_vfs::handles::{OpenAccess, OpenFileTable};
use crate::unix_vfs::index::{InodeTable, child, parent};

impl ResidentFuse {
    pub(in crate::unix_vfs) fn lookup_child(
        &self,
        parent_inode: INodeNo,
        name: &OsStr,
    ) -> Result<(FileAttr, Generation), Errno> {
        let _handles = self.handles.lock().map_err(|_| Errno::EIO)?;
        let mut inodes = self.inodes.lock().map_err(|_| Errno::EIO)?;
        let path = child_path(self, &inodes, parent_inode, name)?;
        let metadata = self.path_metadata(&path)?;
        let (inode, generation) = inodes.record_lookup(&path);
        Ok((self.attr_from_metadata(inode, metadata), generation))
    }

    pub(in crate::unix_vfs) fn create_file_child(
        &self,
        parent_inode: INodeNo,
        name: &OsStr,
        flags: OpenFlags,
    ) -> Result<(FileAttr, Generation, FileHandle), Errno> {
        let access = OpenAccess::from_flags(flags);
        if flags.0 & libc::O_TRUNC != 0 && !access.writable() {
            return Err(Errno::EACCES);
        }
        let mut handles = self.handles.lock().map_err(|_| Errno::EIO)?;
        let mut inodes = self.inodes.lock().map_err(|_| Errno::EIO)?;
        let path = child_path(self, &inodes, parent_inode, name)?;
        if self.contains_unlocked(&path)? {
            return Err(Errno::EEXIST);
        }
        let (inode, generation, handle) = if self.resident.is_scratch(&path) {
            let file = self
                .scratch
                .create_file(&path, flags)
                .map_err(|error| errno("create scratch file", &error))?;
            let inode = inodes.ensure(&path);
            let handle = handles.open_scratch(inode, file, flags);
            let (_, generation) = inodes.record_lookup(&path);
            (inode, generation, handle)
        } else {
            register_resident_create(
                &mut handles,
                &mut inodes,
                &path,
                flags,
                || {
                    self.resident
                        .replace(&path, Vec::new())
                        .map(|_| ())
                        .map_err(|error| errno("create resident file", &error))
                },
                |handles, inode, path, flags| handles.open_resident(inode, path, flags),
                || {
                    self.resident
                        .remove(&path)
                        .map_err(|error| errno("roll back resident file creation", &error))
                },
            )?
        };
        Ok((
            self.make_attr(inode, 0, FileType::RegularFile, 0o644, 1),
            generation,
            handle,
        ))
    }

    pub(in crate::unix_vfs) fn create_directory_child(
        &self,
        parent_inode: INodeNo,
        name: &OsStr,
    ) -> Result<(FileAttr, Generation), Errno> {
        let _handles = self.handles.lock().map_err(|_| Errno::EIO)?;
        let mut inodes = self.inodes.lock().map_err(|_| Errno::EIO)?;
        let path = child_path(self, &inodes, parent_inode, name)?;
        if self.contains_unlocked(&path)? {
            return Err(Errno::EEXIST);
        }
        if self.resident.is_scratch(&path) {
            self.scratch
                .create_directory(&path)
                .map_err(|error| errno("create scratch directory", &error))?;
        } else {
            self.resident
                .create_directory(&path)
                .map_err(|error| errno("create resident directory", &error))?;
        }
        let (inode, generation) = inodes.record_lookup(&path);
        Ok((
            self.make_attr(inode, 0, FileType::Directory, 0o755, 2),
            generation,
        ))
    }

    pub(in crate::unix_vfs) fn directory_entries(
        &self,
        inode: INodeNo,
    ) -> Result<Vec<DirectoryEntry>, Errno> {
        let _handles = self.handles.lock().map_err(|_| Errno::EIO)?;
        let mut inodes = self.inodes.lock().map_err(|_| Errno::EIO)?;
        let path = inodes.path(inode).ok_or(Errno::ENOENT)?;
        if self.path_metadata(&path)?.kind != FileType::Directory {
            return Err(Errno::ENOTDIR);
        }
        let mut entries = vec![
            (inode, FileType::Directory, ".".to_owned()),
            (
                inodes.ensure(parent(&path)),
                FileType::Directory,
                "..".to_owned(),
            ),
        ];
        for (entry_name, directory, _) in self.entries_unlocked(&path)? {
            let Some(child_path) = child(&path, OsStr::new(&entry_name)) else {
                continue;
            };
            entries.push((
                inodes.ensure(&child_path),
                if directory {
                    FileType::Directory
                } else {
                    FileType::RegularFile
                },
                entry_name,
            ));
        }
        Ok(entries)
    }
}

pub(super) fn register_resident_create<C, O, R>(
    handles: &mut OpenFileTable,
    inodes: &mut InodeTable,
    path: &str,
    flags: OpenFlags,
    create: C,
    open: O,
    rollback: R,
) -> Result<(INodeNo, Generation, FileHandle), Errno>
where
    C: FnOnce() -> Result<(), Errno>,
    O: FnOnce(&mut OpenFileTable, INodeNo, &str, OpenFlags) -> Result<FileHandle, Errno>,
    R: FnOnce() -> Result<(), Errno>,
{
    let previous_inode = inodes.inode_for_path(path);
    create()?;
    let inode = inodes.ensure(path);
    let handle = match open(handles, inode, path, flags) {
        Ok(handle) => handle,
        Err(error) => {
            let rollback_result = rollback();
            if previous_inode.is_none() {
                inodes.remove_path(path);
            }
            rollback_result?;
            return Err(error);
        }
    };
    let (_, generation) = inodes.record_lookup(path);
    Ok((inode, generation, handle))
}
