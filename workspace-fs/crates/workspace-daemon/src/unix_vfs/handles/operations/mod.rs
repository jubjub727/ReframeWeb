mod mutation;
mod namespace;

#[cfg(test)]
mod tests;

use std::ffi::OsStr;

use fuser::{Errno, FileType, INodeNo};

use crate::unix_vfs::filesystem::ResidentFuse;
use crate::unix_vfs::index::{InodeTable, child};

pub(in crate::unix_vfs) type DirectoryEntry = (INodeNo, FileType, String);

fn child_path(
    fs: &ResidentFuse,
    inodes: &InodeTable,
    parent_inode: INodeNo,
    name: &OsStr,
) -> Result<String, Errno> {
    let parent = inodes.path(parent_inode).ok_or(Errno::ENOENT)?;
    if fs.path_metadata(&parent)?.kind != FileType::Directory {
        return Err(Errno::ENOTDIR);
    }
    child(&parent, name).ok_or(Errno::EINVAL)
}
