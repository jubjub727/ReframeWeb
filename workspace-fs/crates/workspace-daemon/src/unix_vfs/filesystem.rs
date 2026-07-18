use std::sync::{Arc, Mutex};
use std::time::{Duration, SystemTime};

use fuser::{Errno, FileAttr, FileType, INodeNo};

use super::error::errno;
use super::handles::OpenFileTable;
use super::index::InodeTable;
use super::scratch::ScratchBackend;
use crate::resident::ResidentWorkspace;

// Namespace mutations originate in this provider, so the kernel can retain
// metadata between operations instead of forcing a userspace round-trip for
// every editor stat call.
pub(super) const TTL: Duration = Duration::from_secs(60);

#[derive(Clone, Copy)]
pub(in crate::unix_vfs) struct PathMetadata {
    pub kind: FileType,
    pub size: u64,
    pub perm: u16,
}

pub struct ResidentFuse {
    pub(super) resident: Arc<ResidentWorkspace>,
    pub(super) scratch: ScratchBackend,
    pub(super) inodes: Mutex<InodeTable>,
    pub(super) handles: Mutex<OpenFileTable>,
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
            handles: Mutex::new(OpenFileTable::new()),
            created: SystemTime::now(),
        })
    }

    pub(in crate::unix_vfs) fn path_metadata(&self, path: &str) -> Result<PathMetadata, Errno> {
        let scratch = self.resident.is_scratch(path);
        let metadata = if scratch {
            self.scratch
                .metadata(path)
                .map_err(|error| errno("read scratch metadata", &error))?
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
            (FileType::RegularFile, file.len() as u64, 0o644)
        } else {
            return Err(Errno::ENOENT);
        };
        Ok(PathMetadata { kind, size, perm })
    }

    pub(in crate::unix_vfs) fn attr_from_metadata(
        &self,
        inode: INodeNo,
        metadata: PathMetadata,
    ) -> FileAttr {
        self.make_attr(
            inode,
            metadata.size,
            metadata.kind,
            metadata.perm,
            if metadata.kind == FileType::Directory {
                2
            } else {
                1
            },
        )
    }

    pub(in crate::unix_vfs) fn contains_unlocked(&self, path: &str) -> Result<bool, Errno> {
        match self.path_metadata(path) {
            Ok(_) => Ok(true),
            Err(error) if error.code() == libc::ENOENT => Ok(false),
            Err(error) => Err(error),
        }
    }

    pub(in crate::unix_vfs) fn entries_unlocked(
        &self,
        path: &str,
    ) -> Result<Vec<(String, bool, u64)>, Errno> {
        if self.resident.is_scratch(path) {
            return self
                .scratch
                .entries(path)
                .map_err(|error| errno("read scratch directory", &error));
        }
        let mut entries = self.resident.entries(path);
        let scratch_entries = self
            .scratch
            .entries(path)
            .map_err(|error| errno("read overlaid scratch directory", &error))?;
        for entry in scratch_entries {
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
        Ok(entries)
    }

    pub(in crate::unix_vfs) fn make_attr(
        &self,
        inode: INodeNo,
        size: u64,
        kind: FileType,
        perm: u16,
        nlink: u32,
    ) -> FileAttr {
        FileAttr {
            ino: inode,
            size,
            blocks: 0,
            atime: self.created,
            mtime: self.created,
            ctime: self.created,
            crtime: self.created,
            kind,
            perm,
            nlink,
            uid: unsafe { libc::getuid() },
            gid: unsafe { libc::getgid() },
            rdev: 0,
            blksize: 4096,
            flags: 0,
        }
    }
}
