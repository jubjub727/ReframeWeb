use std::ffi::OsStr;

use fuser::{
    Errno, FileHandle, INodeNo, RenameFlags, ReplyDirectory, ReplyEmpty, ReplyStatfs, Request,
};

use super::super::filesystem::ResidentFuse;

pub(super) fn unlink(
    fs: &ResidentFuse,
    _request: &Request,
    parent: INodeNo,
    name: &OsStr,
    reply: ReplyEmpty,
) {
    complete_empty(fs.remove_child(parent, name, false), reply);
}

pub(super) fn rmdir(
    fs: &ResidentFuse,
    _request: &Request,
    parent: INodeNo,
    name: &OsStr,
    reply: ReplyEmpty,
) {
    complete_empty(fs.remove_child(parent, name, true), reply);
}

#[allow(clippy::too_many_arguments)]
pub(super) fn rename(
    fs: &ResidentFuse,
    _request: &Request,
    parent_inode: INodeNo,
    old_name: &OsStr,
    new_parent_inode: INodeNo,
    new_name: &OsStr,
    flags: RenameFlags,
    reply: ReplyEmpty,
) {
    if !flags.is_empty() {
        reply.error(Errno::EINVAL);
        return;
    }
    complete_empty(
        fs.rename_child(parent_inode, old_name, new_parent_inode, new_name),
        reply,
    );
}

pub(super) fn readdir(
    fs: &ResidentFuse,
    _request: &Request,
    inode: INodeNo,
    _fh: FileHandle,
    offset: u64,
    mut reply: ReplyDirectory,
) {
    let entries = match fs.directory_entries(inode) {
        Ok(entries) => entries,
        Err(error) => {
            reply.error(error);
            return;
        }
    };
    for (index, (entry_inode, kind, entry_name)) in
        entries.into_iter().enumerate().skip(offset as usize)
    {
        if reply.add(entry_inode, index as u64 + 1, kind, entry_name) {
            break;
        }
    }
    reply.ok();
}

pub(super) fn statfs(fs: &ResidentFuse, _request: &Request, _inode: INodeNo, reply: ReplyStatfs) {
    let stats = fs.resident.stats();
    let blocks = stats.bytes.div_ceil(4096).max(1);
    reply.statfs(
        blocks,
        u64::MAX / 4096 - blocks,
        u64::MAX / 4096 - blocks,
        stats.files as u64 + 1,
        u64::MAX / 2,
        4096,
        255,
        4096,
    );
}

fn complete_empty(result: Result<(), Errno>, reply: ReplyEmpty) {
    match result {
        Ok(()) => reply.ok(),
        Err(error) => reply.error(error),
    }
}
