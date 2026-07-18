mod io;
mod metadata;
mod tree;

use std::ffi::OsStr;
use std::time::SystemTime;

use fuser::{
    FileHandle, Filesystem, INodeNo, OpenFlags, RenameFlags, ReplyAttr, ReplyCreate, ReplyData,
    ReplyDirectory, ReplyEmpty, ReplyEntry, ReplyOpen, ReplyStatfs, ReplyWrite, Request, TimeOrNow,
    WriteFlags,
};

use super::filesystem::ResidentFuse;

impl Filesystem for ResidentFuse {
    fn forget(&self, request: &Request, inode: INodeNo, count: u64) {
        metadata::forget(self, request, inode, count);
    }

    fn lookup(&self, request: &Request, parent: INodeNo, name: &OsStr, reply: ReplyEntry) {
        metadata::lookup(self, request, parent, name, reply);
    }

    fn getattr(&self, request: &Request, inode: INodeNo, fh: Option<FileHandle>, reply: ReplyAttr) {
        metadata::getattr(self, request, inode, fh, reply);
    }

    fn setattr(
        &self,
        request: &Request,
        inode: INodeNo,
        mode: Option<u32>,
        uid: Option<u32>,
        gid: Option<u32>,
        size: Option<u64>,
        atime: Option<TimeOrNow>,
        mtime: Option<TimeOrNow>,
        ctime: Option<SystemTime>,
        fh: Option<FileHandle>,
        crtime: Option<SystemTime>,
        chgtime: Option<SystemTime>,
        bkuptime: Option<SystemTime>,
        flags: Option<fuser::BsdFileFlags>,
        reply: ReplyAttr,
    ) {
        metadata::setattr(
            self, request, inode, mode, uid, gid, size, atime, mtime, ctime, fh, crtime, chgtime,
            bkuptime, flags, reply,
        );
    }

    fn mkdir(
        &self,
        request: &Request,
        parent: INodeNo,
        name: &OsStr,
        mode: u32,
        umask: u32,
        reply: ReplyEntry,
    ) {
        metadata::mkdir(self, request, parent, name, mode, umask, reply);
    }

    fn create(
        &self,
        request: &Request,
        parent: INodeNo,
        name: &OsStr,
        mode: u32,
        umask: u32,
        flags: i32,
        reply: ReplyCreate,
    ) {
        metadata::create(self, request, parent, name, mode, umask, flags, reply);
    }

    fn open(&self, request: &Request, inode: INodeNo, flags: OpenFlags, reply: ReplyOpen) {
        metadata::open(self, request, inode, flags, reply);
    }

    fn read(
        &self,
        request: &Request,
        inode: INodeNo,
        fh: FileHandle,
        offset: u64,
        size: u32,
        flags: OpenFlags,
        lock_owner: Option<fuser::LockOwner>,
        reply: ReplyData,
    ) {
        io::read(
            self, request, inode, fh, offset, size, flags, lock_owner, reply,
        );
    }

    fn write(
        &self,
        request: &Request,
        inode: INodeNo,
        fh: FileHandle,
        offset: u64,
        data: &[u8],
        write_flags: WriteFlags,
        flags: OpenFlags,
        lock_owner: Option<fuser::LockOwner>,
        reply: ReplyWrite,
    ) {
        io::write(
            self,
            request,
            inode,
            fh,
            offset,
            data,
            write_flags,
            flags,
            lock_owner,
            reply,
        );
    }

    fn unlink(&self, request: &Request, parent: INodeNo, name: &OsStr, reply: ReplyEmpty) {
        tree::unlink(self, request, parent, name, reply);
    }

    fn rmdir(&self, request: &Request, parent: INodeNo, name: &OsStr, reply: ReplyEmpty) {
        tree::rmdir(self, request, parent, name, reply);
    }

    fn rename(
        &self,
        request: &Request,
        parent: INodeNo,
        old_name: &OsStr,
        new_parent: INodeNo,
        new_name: &OsStr,
        flags: RenameFlags,
        reply: ReplyEmpty,
    ) {
        tree::rename(
            self, request, parent, old_name, new_parent, new_name, flags, reply,
        );
    }

    fn readdir(
        &self,
        request: &Request,
        inode: INodeNo,
        fh: FileHandle,
        offset: u64,
        reply: ReplyDirectory,
    ) {
        tree::readdir(self, request, inode, fh, offset, reply);
    }

    fn flush(
        &self,
        request: &Request,
        inode: INodeNo,
        fh: FileHandle,
        owner: fuser::LockOwner,
        reply: ReplyEmpty,
    ) {
        io::flush(self, request, inode, fh, owner, reply);
    }

    fn release(
        &self,
        request: &Request,
        inode: INodeNo,
        fh: FileHandle,
        flags: OpenFlags,
        lock_owner: Option<fuser::LockOwner>,
        flush: bool,
        reply: ReplyEmpty,
    ) {
        io::release(self, request, inode, fh, flags, lock_owner, flush, reply);
    }

    fn fsync(
        &self,
        request: &Request,
        inode: INodeNo,
        fh: FileHandle,
        datasync: bool,
        reply: ReplyEmpty,
    ) {
        io::fsync(self, request, inode, fh, datasync, reply);
    }

    fn statfs(&self, request: &Request, inode: INodeNo, reply: ReplyStatfs) {
        tree::statfs(self, request, inode, reply);
    }
}
