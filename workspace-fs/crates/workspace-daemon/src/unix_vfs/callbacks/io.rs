use fuser::{
    Errno, FileHandle, INodeNo, OpenFlags, ReplyData, ReplyEmpty, ReplyWrite, Request, WriteFlags,
};

use super::super::error::errno;
use super::super::filesystem::ResidentFuse;

#[allow(clippy::too_many_arguments)]
pub(super) fn read(
    fs: &ResidentFuse,
    _request: &Request,
    inode: INodeNo,
    fh: FileHandle,
    offset: u64,
    size: u32,
    _flags: OpenFlags,
    _lock_owner: Option<fuser::LockOwner>,
    reply: ReplyData,
) {
    let result = fs.handle(inode, fh).and_then(|handle| {
        handle.read(offset, size, |path| {
            fs.resident
                .file(path)
                .map(|file| file.bytes.to_vec())
                .ok_or(Errno::ENOENT)
        })
    });
    match result {
        Ok(bytes) => reply.data(&bytes),
        Err(error) => reply.error(error),
    }
}

#[allow(clippy::too_many_arguments)]
pub(super) fn write(
    fs: &ResidentFuse,
    _request: &Request,
    inode: INodeNo,
    fh: FileHandle,
    offset: u64,
    data: &[u8],
    _write_flags: WriteFlags,
    _flags: OpenFlags,
    _lock_owner: Option<fuser::LockOwner>,
    reply: ReplyWrite,
) {
    let result = fs.handle(inode, fh).and_then(|handle| {
        handle.write(offset, data, |path, offset, data| {
            fs.resident
                .write(path, offset, data)
                .map(|_| ())
                .map_err(|error| errno("write resident file", &error))
        })
    });
    match result {
        Ok(()) => reply.written(data.len() as u32),
        Err(error) => reply.error(error),
    }
}

pub(super) fn flush(
    fs: &ResidentFuse,
    _request: &Request,
    inode: INodeNo,
    fh: FileHandle,
    _owner: fuser::LockOwner,
    reply: ReplyEmpty,
) {
    complete_empty(fs.handle(inode, fh).map(|_| ()), reply);
}

#[allow(clippy::too_many_arguments)]
pub(super) fn release(
    fs: &ResidentFuse,
    _request: &Request,
    inode: INodeNo,
    fh: FileHandle,
    _flags: OpenFlags,
    _lock_owner: Option<fuser::LockOwner>,
    _flush: bool,
    reply: ReplyEmpty,
) {
    let result = fs
        .handles
        .lock()
        .map_err(|_| Errno::EIO)
        .and_then(|mut handles| handles.release(fh, inode));
    complete_empty(result, reply);
}

pub(super) fn fsync(
    fs: &ResidentFuse,
    _request: &Request,
    inode: INodeNo,
    fh: FileHandle,
    datasync: bool,
    reply: ReplyEmpty,
) {
    let result = fs
        .handle(inode, fh)
        .and_then(|handle| handle.sync(datasync));
    complete_empty(result, reply);
}

fn complete_empty(result: Result<(), Errno>, reply: ReplyEmpty) {
    match result {
        Ok(()) => reply.ok(),
        Err(error) => reply.error(error),
    }
}
