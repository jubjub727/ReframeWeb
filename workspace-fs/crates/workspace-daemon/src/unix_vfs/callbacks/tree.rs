    fn unlink(&self, _request: &Request, parent: INodeNo, name: &OsStr, reply: ReplyEmpty) {
        self.remove_child(parent, name, false, reply);
    }

    fn rmdir(&self, _request: &Request, parent: INodeNo, name: &OsStr, reply: ReplyEmpty) {
        self.remove_child(parent, name, true, reply);
    }

    fn rename(
        &self,
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
        let result = self.child_path(parent_inode, old_name).and_then(|source| {
            let destination = self.child_path(new_parent_inode, new_name)?;
            let source_scratch = self.resident.is_scratch(&source);
            let destination_scratch = self.resident.is_scratch(&destination);
            ensure_same_storage(source_scratch, destination_scratch).map_err(|_| Errno::EXDEV)?;
            if source_scratch {
                self.scratch
                    .rename(&source, &destination)
                    .map_err(|_| Errno::EIO)?;
            } else {
                self.resident
                    .rename(&source, &destination)
                    .map_err(|_| Errno::EIO)?;
            }
            self.inodes
                .lock()
                .map_err(|_| Errno::EIO)?
                .move_path(&source, &destination);
            Ok(())
        });
        match result {
            Ok(()) => reply.ok(),
            Err(error) => reply.error(error),
        }
    }

    fn readdir(
        &self,
        _request: &Request,
        inode: INodeNo,
        _fh: FileHandle,
        offset: u64,
        mut reply: ReplyDirectory,
    ) {
        let Ok(path) = self.path(inode) else {
            reply.error(Errno::ENOENT);
            return;
        };
        let mut entries = vec![
            (inode, FileType::Directory, ".".to_owned()),
            (
                self.inode(parent(&path)).unwrap_or(ROOT_INODE),
                FileType::Directory,
                "..".to_owned(),
            ),
        ];
        for (entry_name, directory, _) in self.entries(&path) {
            let child_path = child(&path, OsStr::new(&entry_name)).unwrap_or_default();
            if let Ok(child_inode) = self.inode(&child_path) {
                entries.push((
                    child_inode,
                    if directory {
                        FileType::Directory
                    } else {
                        FileType::RegularFile
                    },
                    entry_name,
                ));
            }
        }
        for (index, (entry_inode, kind, entry_name)) in
            entries.into_iter().enumerate().skip(offset as usize)
        {
            if reply.add(entry_inode, index as u64 + 1, kind, entry_name) {
                break;
            }
        }
        reply.ok();
    }

    fn flush(
        &self,
        _request: &Request,
        _inode: INodeNo,
        _fh: FileHandle,
        _owner: fuser::LockOwner,
        reply: ReplyEmpty,
    ) {
        reply.ok();
    }

    fn fsync(
        &self,
        _request: &Request,
        _inode: INodeNo,
        _fh: FileHandle,
        _datasync: bool,
        reply: ReplyEmpty,
    ) {
        reply.ok();
    }

    fn statfs(&self, _request: &Request, _inode: INodeNo, reply: ReplyStatfs) {
        let stats = self.resident.stats();
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
}
