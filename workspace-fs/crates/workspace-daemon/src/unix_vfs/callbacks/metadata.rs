use std::ffi::OsStr;
use std::time::SystemTime;

use fuser::{
    FileHandle, FopenFlags, INodeNo, OpenFlags, ReplyAttr, ReplyCreate, ReplyEntry, ReplyOpen,
    Request, TimeOrNow,
};

use super::super::filesystem::{ResidentFuse, TTL};

pub(super) fn forget(fs: &ResidentFuse, _request: &Request, inode: INodeNo, count: u64) {
    if let Ok(mut inodes) = fs.inodes.lock() {
        inodes.forget(inode, count);
    }
}

pub(super) fn lookup(
    fs: &ResidentFuse,
    _request: &Request,
    parent: INodeNo,
    name: &OsStr,
    reply: ReplyEntry,
) {
    match fs.lookup_child(parent, name) {
        Ok((attr, generation)) => reply.entry(&TTL, &attr, generation),
        Err(error) => reply.error(error),
    }
}

pub(super) fn getattr(
    fs: &ResidentFuse,
    _request: &Request,
    inode: INodeNo,
    fh: Option<FileHandle>,
    reply: ReplyAttr,
) {
    match fs.getattr_inode(inode, fh) {
        Ok(attr) => reply.attr(&TTL, &attr),
        Err(error) => reply.error(error),
    }
}

#[allow(clippy::too_many_arguments)]
pub(super) fn setattr(
    fs: &ResidentFuse,
    _request: &Request,
    inode: INodeNo,
    _mode: Option<u32>,
    _uid: Option<u32>,
    _gid: Option<u32>,
    size: Option<u64>,
    _atime: Option<TimeOrNow>,
    _mtime: Option<TimeOrNow>,
    _ctime: Option<SystemTime>,
    fh: Option<FileHandle>,
    _crtime: Option<SystemTime>,
    _chgtime: Option<SystemTime>,
    _bkuptime: Option<SystemTime>,
    _flags: Option<fuser::BsdFileFlags>,
    reply: ReplyAttr,
) {
    match fs.setattr_inode(inode, fh, size) {
        Ok(attr) => reply.attr(&TTL, &attr),
        Err(error) => reply.error(error),
    }
}

pub(super) fn mkdir(
    fs: &ResidentFuse,
    _request: &Request,
    parent: INodeNo,
    name: &OsStr,
    _mode: u32,
    _umask: u32,
    reply: ReplyEntry,
) {
    match fs.create_directory_child(parent, name) {
        Ok((attr, generation)) => reply.entry(&TTL, &attr, generation),
        Err(error) => reply.error(error),
    }
}

#[allow(clippy::too_many_arguments)]
pub(super) fn create(
    fs: &ResidentFuse,
    _request: &Request,
    parent: INodeNo,
    name: &OsStr,
    _mode: u32,
    _umask: u32,
    flags: i32,
    reply: ReplyCreate,
) {
    match fs.create_file_child(parent, name, OpenFlags(flags)) {
        Ok((attr, generation, handle)) => reply.created(
            &TTL,
            &attr,
            generation,
            handle,
            FopenFlags::FOPEN_KEEP_CACHE,
        ),
        Err(error) => reply.error(error),
    }
}

pub(super) fn open(
    fs: &ResidentFuse,
    _request: &Request,
    inode: INodeNo,
    flags: OpenFlags,
    reply: ReplyOpen,
) {
    match fs.open_inode(inode, flags) {
        Ok(handle) => reply.opened(handle, FopenFlags::FOPEN_KEEP_CACHE),
        Err(error) => reply.error(error),
    }
}
