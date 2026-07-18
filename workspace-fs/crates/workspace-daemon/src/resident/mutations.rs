impl ResidentWorkspace {
    #[cfg_attr(windows, allow(dead_code))]
    pub fn is_directory(&self, path: &str) -> bool {
        path.is_empty()
            || self
                .directories
                .read()
                .map(|directories| directories.contains(path))
                .unwrap_or(false)
    }

    #[cfg_attr(windows, allow(dead_code))]
    pub fn create_directory(&self, path: &str) -> Result<()> {
        if self.scratch.matches(path) {
            bail!("scratch content cannot enter the resident workspace: {path}");
        }
        let mut directories = self.directories.write().map_err(lock_error)?;
        add_parent_directories(&mut directories, path);
        directories.insert(path.to_owned());
        Ok(())
    }

    pub fn replace(&self, path: &str, bytes: Vec<u8>) -> Result<ChangeKind> {
        if self.scratch.matches(path) {
            bail!("scratch content cannot enter the resident workspace: {path}");
        }
        let hash = blake3::hash(&bytes).to_hex().to_string();
        let kind = if self.baseline.read().map_err(lock_error)?.contains_key(path) {
            ChangeKind::Write
        } else {
            ChangeKind::Create
        };
        self.files.write().map_err(lock_error)?.insert(
            path.to_owned(),
            ResidentFile { bytes: bytes.into(), hash },
        );
        let mut directories = self.directories.write().map_err(lock_error)?;
        add_parent_directories(&mut directories, path);
        drop(directories);
        self.deleted.write().map_err(lock_error)?.remove(path);
        Ok(kind)
    }

    #[cfg_attr(windows, allow(dead_code))]
    pub fn write(&self, path: &str, offset: u64, data: &[u8]) -> Result<ChangeKind> {
        let mut bytes = self.file(path).map(|file| file.bytes.to_vec()).unwrap_or_default();
        let offset = usize::try_from(offset).context("write offset exceeds address space")?;
        if bytes.len() < offset {
            bytes.resize(offset, 0);
        }
        let end = offset.checked_add(data.len()).context("write length overflow")?;
        if bytes.len() < end {
            bytes.resize(end, 0);
        }
        bytes[offset..end].copy_from_slice(data);
        self.replace(path, bytes)
    }

    #[cfg_attr(windows, allow(dead_code))]
    pub fn resize(&self, path: &str, size: u64) -> Result<ChangeKind> {
        let mut bytes = self.file(path).map(|file| file.bytes.to_vec()).unwrap_or_default();
        bytes.resize(usize::try_from(size).context("file size exceeds address space")?, 0);
        self.replace(path, bytes)
    }

    pub fn remove(&self, path: &str) -> Result<()> {
        if self.scratch.matches(path) {
            return Ok(());
        }
        let prefix = format!("{path}/");
        self.files.write().map_err(lock_error)?.retain(|candidate, _| candidate != path && !candidate.starts_with(&prefix));
        self.directories.write().map_err(lock_error)?.retain(|candidate| candidate != path && !candidate.starts_with(&prefix));
        let mut deleted = self.deleted.write().map_err(lock_error)?;
        let baseline = self.baseline.read().map_err(lock_error)?;
        for baseline in baseline.keys() {
            if baseline == path || baseline.starts_with(&prefix) {
                deleted.insert(baseline.clone());
            }
        }
        Ok(())
    }

    pub fn rename(&self, source: &str, destination: &str) -> Result<()> {
        if self.scratch.matches(source) || self.scratch.matches(destination) {
            bail!("cannot rename between resident and direct-disk paths");
        }
        let prefix = format!("{source}/");
        let replacements = {
            let files = self.files.read().map_err(lock_error)?;
            files.iter().filter_map(|(path, file)| {
                if path == source {
                    Some((path.clone(), destination.to_owned(), file.clone()))
                } else {
                    path.strip_prefix(&prefix).map(|relative| (path.clone(), format!("{destination}/{relative}"), file.clone()))
                }
            }).collect::<Vec<_>>()
        };
        let directory_replacements = {
            let directories = self.directories.read().map_err(lock_error)?;
            directories.iter().filter_map(|path| {
                if path == source {
                    Some((path.clone(), destination.to_owned()))
                } else {
                    path.strip_prefix(&prefix).map(|relative| (path.clone(), format!("{destination}/{relative}")))
                }
            }).collect::<Vec<_>>()
        };
        if replacements.is_empty() && directory_replacements.is_empty() {
            bail!("rename source does not exist: {source}");
        }
        let mut files = self.files.write().map_err(lock_error)?;
        for (old, new, file) in replacements {
            files.remove(&old);
            files.insert(new, file);
        }
        drop(files);
        let mut directories = self.directories.write().map_err(lock_error)?;
        for (old, new) in directory_replacements {
            directories.remove(&old);
            directories.insert(new);
        }
        add_parent_directories(&mut directories, destination);
        drop(directories);
        let mut deleted = self.deleted.write().map_err(lock_error)?;
        let baseline = self.baseline.read().map_err(lock_error)?;
        for baseline in baseline.keys() {
            if baseline == source || baseline.starts_with(&prefix) {
                deleted.insert(baseline.clone());
            }
        }
        Ok(())
    }

    pub fn changes(&self) -> Vec<Change> {
        let (Ok(files), Ok(baseline)) = (self.files.read(), self.baseline.read()) else {
            return Vec::new();
        };
        let deleted = self.deleted.read().ok();
        let mut changes = Vec::new();
        for (path, file) in files.iter() {
            match baseline.get(path) {
                None => changes.push(Change { path: path.clone(), kind: ChangeKind::Create, size: Some(file.bytes.len() as u64) }),
                Some(original) if original.hash != file.hash => changes.push(Change { path: path.clone(), kind: ChangeKind::Write, size: Some(file.bytes.len() as u64) }),
                _ => {}
            }
        }
        if let Ok(directories) = self.directories.read() {
            for path in directories.iter() {
                let prefix = format!("{path}/");
                if !baseline.contains_key(path)
                    && !baseline.keys().any(|candidate| candidate.starts_with(&prefix))
                {
                    changes.push(Change {
                        path: path.clone(),
                        kind: ChangeKind::Create,
                        size: None,
                    });
                }
            }
        }
        if let Some(deleted) = deleted {
            changes.extend(deleted.iter().map(|path| Change { path: path.clone(), kind: ChangeKind::Delete, size: None }));
        }
        changes.sort_by(|left, right| left.path.cmp(&right.path));
        changes
    }

    pub fn mark_checkpointed(&self, paths: &[String]) -> Result<()> {
        let files = self.files.read().map_err(lock_error)?;
        let mut baseline = self.baseline.write().map_err(lock_error)?;
        let mut deleted = self.deleted.write().map_err(lock_error)?;
        for path in paths {
            if let Some(file) = files.get(path) {
                baseline.insert(path.clone(), FileRecord {
                    path: path.clone(), hash: file.hash.clone(), size: file.bytes.len() as u64,
                    source_kind: "resident".into(), source_ref: None,
                });
            } else if self.is_directory(path) {
                baseline.insert(
                    path.clone(),
                    FileRecord {
                        path: path.clone(),
                        hash: String::new(),
                        size: 0,
                        source_kind: "directory".into(),
                        source_ref: None,
                    },
                );
            } else {
                baseline.remove(path);
            }
            deleted.remove(path);
        }
        Ok(())
    }
}
