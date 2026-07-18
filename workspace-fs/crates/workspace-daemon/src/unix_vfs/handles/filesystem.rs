use fuser::{Errno, FileAttr, FileHandle, FileType, INodeNo, OpenFlags};

use super::{OpenAccess, OpenHandle};
use crate::unix_vfs::error::errno;
use crate::unix_vfs::filesystem::ResidentFuse;

impl ResidentFuse {
    pub(in crate::unix_vfs) fn open_inode(
        &self,
        inode: INodeNo,
        flags: OpenFlags,
    ) -> Result<FileHandle, Errno> {
        let access = OpenAccess::from_flags(flags);
        if flags.0 & libc::O_TRUNC != 0 && !access.writable() {
            return Err(Errno::EACCES);
        }
        let mut handles = self.handles.lock().map_err(|_| Errno::EIO)?;
        let inodes = self.inodes.lock().map_err(|_| Errno::EIO)?;
        let path = inodes.path(inode).ok_or(Errno::ENOENT)?;
        let metadata = self.path_metadata(&path)?;
        if metadata.kind == FileType::Directory {
            return Err(Errno::EISDIR);
        }
        if self.resident.is_scratch(&path) {
            let file = self
                .scratch
                .open(&path, flags)
                .map_err(|error| errno("open scratch file", &error))?;
            return Ok(handles.open_scratch(inode, file, flags));
        }
        if flags.0 & libc::O_TRUNC != 0 {
            self.resident
                .resize(&path, 0)
                .map_err(|error| errno("truncate resident file", &error))?;
        }
        handles.open_resident(inode, &path, flags)
    }

    pub(in crate::unix_vfs) fn handle(
        &self,
        inode: INodeNo,
        handle: FileHandle,
    ) -> Result<OpenHandle, Errno> {
        self.handles
            .lock()
            .map_err(|_| Errno::EIO)?
            .get(handle, inode)
    }

    pub(in crate::unix_vfs) fn getattr_inode(
        &self,
        inode: INodeNo,
        file_handle: Option<FileHandle>,
    ) -> Result<FileAttr, Errno> {
        let handles = self.handles.lock().map_err(|_| Errno::EIO)?;
        let inodes = self.inodes.lock().map_err(|_| Errno::EIO)?;
        if let Some(file_handle) = file_handle {
            let handle = handles.get(file_handle, inode)?;
            return self.open_handle_attr(&inodes, inode, &handle);
        }
        let path = inodes.path(inode).ok_or(Errno::ENOENT)?;
        let metadata = self.path_metadata(&path)?;
        Ok(self.attr_from_metadata(inode, metadata))
    }

    pub(in crate::unix_vfs) fn setattr_inode(
        &self,
        inode: INodeNo,
        file_handle: Option<FileHandle>,
        size: Option<u64>,
    ) -> Result<FileAttr, Errno> {
        let handles = self.handles.lock().map_err(|_| Errno::EIO)?;
        let inodes = self.inodes.lock().map_err(|_| Errno::EIO)?;
        if let Some(file_handle) = file_handle {
            let handle = handles.get(file_handle, inode)?;
            if let Some(size) = size {
                handle.resize(size, |path, size| {
                    self.resident
                        .resize(path, size)
                        .map(|_| ())
                        .map_err(|error| errno("resize resident file", &error))
                })?;
            }
            return self.open_handle_attr(&inodes, inode, &handle);
        }
        let path = inodes.path(inode).ok_or(Errno::ENOENT)?;
        let mut metadata = self.path_metadata(&path)?;
        if let Some(size) = size {
            if metadata.kind == FileType::Directory {
                return Err(Errno::EISDIR);
            }
            if self.resident.is_scratch(&path) {
                self.scratch
                    .resize_path(&path, size)
                    .map_err(|error| errno("resize scratch file", &error))?;
            } else {
                self.resident
                    .resize(&path, size)
                    .map_err(|error| errno("resize resident file", &error))?;
            }
            metadata.size = size;
        }
        Ok(self.attr_from_metadata(inode, metadata))
    }

    fn open_handle_attr(
        &self,
        inodes: &crate::unix_vfs::index::InodeTable,
        inode: INodeNo,
        handle: &OpenHandle,
    ) -> Result<FileAttr, Errno> {
        let size = handle.len(|path| {
            self.resident
                .file(path)
                .map(|file| file.len() as u64)
                .ok_or(Errno::ENOENT)
        })?;
        Ok(self.make_attr(
            inode,
            size,
            FileType::RegularFile,
            0o644,
            u32::from(inodes.path(inode).is_some()),
        ))
    }
}
