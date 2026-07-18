use std::ffi::OsStr;
use std::sync::{Arc, Mutex};
use std::time::{Duration, SystemTime};

use fuser::{
    Errno, FileAttr, FileHandle, FileType, Filesystem, FopenFlags, Generation, INodeNo, OpenFlags,
    RenameFlags, ReplyAttr, ReplyCreate, ReplyData, ReplyDirectory, ReplyEmpty, ReplyEntry,
    ReplyOpen, ReplyStatfs, ReplyWrite, Request, TimeOrNow, WriteFlags,
};

use super::index::{InodeTable, ROOT_INODE, child, parent};
use super::scratch::{ScratchBackend, ensure_same_storage};
use crate::resident::ResidentWorkspace;

const TTL: Duration = Duration::from_millis(50);

pub struct ResidentFuse {
    resident: Arc<ResidentWorkspace>,
    scratch: ScratchBackend,
    inodes: Mutex<InodeTable>,
    created: SystemTime,
}

impl ResidentFuse {
    pub fn new(
        resident: Arc<ResidentWorkspace>,
        scratch_root: std::path::PathBuf,
    ) -> anyhow::Result<Self> {
        Ok(Self {
            resident,
            scratch: ScratchBackend::new(scratch_root)?,
            inodes: Mutex::new(InodeTable::new()),
            created: SystemTime::now(),
        })
    }

    fn path(&self, inode: INodeNo) -> Result<String, Errno> {
        self.inodes
            .lock()
            .map_err(|_| Errno::EIO)?
            .path(inode)
            .ok_or(Errno::ENOENT)
    }

    fn child_path(&self, parent: INodeNo, name: &OsStr) -> Result<String, Errno> {
        let parent = self.path(parent)?;
        child(&parent, name).ok_or(Errno::EINVAL)
    }

    fn inode(&self, path: &str) -> Result<INodeNo, Errno> {
        Ok(self.inodes.lock().map_err(|_| Errno::EIO)?.ensure(path))
    }

    fn attr(&self, path: &str) -> Result<FileAttr, Errno> {
        let scratch = self.resident.is_scratch(path);
        let metadata = if scratch {
            self.scratch.metadata(path)
        } else {
            None
        };
        let (kind, size, perm) = if metadata.as_ref().is_some_and(std::fs::Metadata::is_dir)
            || (!scratch && self.resident.is_directory(path))
        {
            (FileType::Directory, 0, 0o755)
        } else if let Some(metadata) = metadata {
            (FileType::RegularFile, metadata.len(), 0o644)
        } else if let Some(file) = (!scratch).then(|| self.resident.file(path)).flatten() {
            (FileType::RegularFile, file.bytes.len() as u64, 0o644)
        } else {
            return Err(Errno::ENOENT);
        };
        Ok(FileAttr {
            ino: self.inode(path)?,
            size,
            blocks: 0,
            atime: self.created,
            mtime: self.created,
            ctime: self.created,
            crtime: self.created,
            kind,
            perm,
            nlink: if kind == FileType::Directory { 2 } else { 1 },
            uid: unsafe { libc::getuid() },
            gid: unsafe { libc::getgid() },
            rdev: 0,
            blksize: 4096,
            flags: 0,
        })
    }

    fn reply_entry(&self, path: &str, reply: ReplyEntry) {
        match self.attr(path) {
            Ok(attr) => reply.entry(&TTL, &attr, Generation(0)),
            Err(error) => reply.error(error),
        }
    }

    fn contains(&self, path: &str) -> bool {
        if self.resident.is_scratch(path) {
            self.scratch.metadata(path).is_some()
        } else {
            self.resident.contains_path(path)
        }
    }

    fn entries(&self, path: &str) -> Vec<(String, bool, u64)> {
        if self.resident.is_scratch(path) {
            self.scratch.entries(path).unwrap_or_default()
        } else {
            let mut entries = self.resident.entries(path);
            for entry in self.scratch.entries(path).unwrap_or_default() {
                let child = if path.is_empty() {
                    entry.0.clone()
                } else {
                    format!("{path}/{}", entry.0)
                };
                if self.resident.is_scratch(&child)
                    && !entries.iter().any(|existing| existing.0 == entry.0)
                {
                    entries.push(entry);
                }
            }
            entries.sort_by(|left, right| left.0.cmp(&right.0));
            entries
        }
    }
}

impl Filesystem for ResidentFuse {
    include!("callbacks/metadata.rs");
    include!("callbacks/io.rs");
    include!("callbacks/tree.rs");
}
impl ResidentFuse {
    fn remove_child(
        &self,
        parent_inode: INodeNo,
        entry_name: &OsStr,
        directory: bool,
        reply: ReplyEmpty,
    ) {
        let result = self.child_path(parent_inode, entry_name).and_then(|path| {
            let scratch = self.resident.is_scratch(&path);
            let is_directory = self
                .attr(&path)
                .is_ok_and(|attr| attr.kind == FileType::Directory);
            if directory {
                if !is_directory {
                    return Err(Errno::ENOTDIR);
                }
                if !self.entries(&path).is_empty() {
                    return Err(Errno::ENOTEMPTY);
                }
            } else if is_directory {
                return Err(Errno::EISDIR);
            } else if !self.contains(&path) {
                return Err(Errno::ENOENT);
            }
            if scratch {
                self.scratch
                    .remove(&path, directory)
                    .map_err(|_| Errno::EIO)
            } else {
                self.resident.remove(&path).map_err(|_| Errno::EIO)
            }
        });
        match result {
            Ok(()) => reply.ok(),
            Err(error) => reply.error(error),
        }
    }
}
