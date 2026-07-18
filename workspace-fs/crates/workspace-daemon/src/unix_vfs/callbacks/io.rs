    fn open(&self, _request: &Request, inode: INodeNo, _flags: OpenFlags, reply: ReplyOpen) {
        match self.path(inode) {
            Ok(path)
                if self.contains(&path)
                    && !self
                        .attr(&path)
                        .is_ok_and(|attr| attr.kind == FileType::Directory) =>
            {
                reply.opened(FileHandle(inode.0), FopenFlags::FOPEN_DIRECT_IO)
            }
            _ => reply.error(Errno::ENOENT),
        }
}
    fn read(
        &self,
        _request: &Request,
        inode: INodeNo,
        _fh: FileHandle,
        offset: u64,
        size: u32,
        _flags: OpenFlags,
        _lock_owner: Option<fuser::LockOwner>,
        reply: ReplyData,
    ) {
        let result = self.path(inode).and_then(|path| {
            if self.resident.is_scratch(&path) {
                return self
                    .scratch
                    .read(&path, offset, size)
                    .map_err(|_| Errno::EIO);
            }
            let file = self.resident.file(&path).ok_or(Errno::ENOENT)?;
            let start = usize::try_from(offset).map_err(|_| Errno::EINVAL)?;
            if start >= file.bytes.len() {
                return Ok(Vec::new());
            }
            let end = start.saturating_add(size as usize).min(file.bytes.len());
            Ok(file.bytes[start..end].to_vec())
        });
        match result {
            Ok(bytes) => reply.data(&bytes),
            Err(error) => reply.error(error),
        }
    }
    fn write(
        &self,
        _request: &Request,
        inode: INodeNo,
        _fh: FileHandle,
        offset: u64,
        data: &[u8],
        _write_flags: WriteFlags,
        _flags: OpenFlags,
        _lock_owner: Option<fuser::LockOwner>,
        reply: ReplyWrite,
    ) {
        match self.path(inode).and_then(|path| {
            if self.resident.is_scratch(&path) {
                self.scratch
                    .write(&path, offset, data)
                    .map_err(|_| Errno::EIO)
            } else {
                self.resident
                    .write(&path, offset, data)
                    .map(|_| ())
                    .map_err(|_| Errno::EIO)
            }
        }) {
            Ok(_) => reply.written(data.len() as u32),
            Err(error) => reply.error(error),
        }
    }
