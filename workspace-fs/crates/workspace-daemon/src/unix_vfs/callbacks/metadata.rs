    fn lookup(&self, _request: &Request, parent: INodeNo, name: &OsStr, reply: ReplyEntry) {
        match self.child_path(parent, name) {
            Ok(path) if self.contains(&path) => self.reply_entry(&path, reply),
            Ok(_) => reply.error(Errno::ENOENT),
            Err(error) => reply.error(error),
        }
}
    fn getattr(
        &self,
        _request: &Request,
        inode: INodeNo,
        _fh: Option<FileHandle>,
        reply: ReplyAttr,
    ) {
        match self.path(inode).and_then(|path| self.attr(&path)) {
            Ok(attr) => reply.attr(&TTL, &attr),
            Err(error) => reply.error(error),
        }
    }
    fn setattr(
        &self,
        _request: &Request,
        inode: INodeNo,
        _mode: Option<u32>,
        _uid: Option<u32>,
        _gid: Option<u32>,
        size: Option<u64>,
        _atime: Option<TimeOrNow>,
        _mtime: Option<TimeOrNow>,
        _ctime: Option<SystemTime>,
        _fh: Option<FileHandle>,
        _crtime: Option<SystemTime>,
        _chgtime: Option<SystemTime>,
        _bkuptime: Option<SystemTime>,
        _flags: Option<fuser::BsdFileFlags>,
        reply: ReplyAttr,
    ) {
        let result = self.path(inode).and_then(|path| {
            if let Some(size) = size {
                if self.resident.is_scratch(&path) {
                    self.scratch.resize(&path, size).map_err(|_| Errno::EIO)?;
                } else {
                    self.resident.resize(&path, size).map_err(|_| Errno::EIO)?;
                }
            }
            self.attr(&path)
        });
        match result {
            Ok(attr) => reply.attr(&TTL, &attr),
            Err(error) => reply.error(error),
        }
    }

    fn mkdir(
        &self,
        _request: &Request,
        parent: INodeNo,
        name: &OsStr,
        _mode: u32,
        _umask: u32,
        reply: ReplyEntry,
    ) {
        match self.child_path(parent, name) {
            Ok(path) if self.contains(&path) => reply.error(Errno::EEXIST),
            Ok(path) => match if self.resident.is_scratch(&path) {
                self.scratch.create_directory(&path)
            } else {
                self.resident.create_directory(&path)
            } {
                Ok(()) => self.reply_entry(&path, reply),
                Err(_) => reply.error(Errno::EIO),
            },
            Err(error) => reply.error(error),
        }
    }

    fn create(
        &self,
        _request: &Request,
        parent: INodeNo,
        name: &OsStr,
        _mode: u32,
        _umask: u32,
        _flags: i32,
        reply: ReplyCreate,
    ) {
        let result = self.child_path(parent, name).and_then(|path| {
            if self.contains(&path) {
                return Err(Errno::EEXIST);
            }
            if self.resident.is_scratch(&path) {
                self.scratch.create_file(&path).map_err(|_| Errno::EIO)?;
            } else {
                self.resident
                    .replace(&path, Vec::new())
                    .map_err(|_| Errno::EIO)?;
            }
            Ok((path.clone(), self.attr(&path)?))
        });
        match result {
            Ok((_path, attr)) => reply.created(
                &TTL,
                &attr,
                Generation(0),
                FileHandle(attr.ino.0),
                FopenFlags::FOPEN_DIRECT_IO,
            ),
            Err(error) => reply.error(error),
        }
    }
