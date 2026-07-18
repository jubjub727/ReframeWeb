use anyhow::{Context, Result, bail};

use crate::model::{Change, ChangeKind, FileRecord, RecordSource};
use crate::paths::NormalizedPath;

use super::{ResidentWorkspace, add_parent_directories, lock_error};

impl ResidentWorkspace {
    #[cfg_attr(windows, allow(dead_code))]
    pub fn is_directory(&self, path: &str) -> bool {
        path.is_empty()
            || self
                .state
                .read()
                .map(|state| state.directories.contains(path))
                .unwrap_or(false)
    }

    #[cfg_attr(windows, allow(dead_code))]
    pub fn create_directory(&self, path: &str) -> Result<()> {
        self.reject_scratch(path)?;
        let path = NormalizedPath::parse_str(path)?;
        let mut state = self.state.write().map_err(lock_error)?;
        if state.files.contains_key(path.as_str()) {
            bail!("cannot create a directory over a resident file: {path}");
        }
        add_parent_directories(&mut state.directories, path.as_str())?;
        state.directories.insert(path);
        state.rebuild_changes();
        Ok(())
    }

    pub fn replace(&self, path: &str, bytes: Vec<u8>) -> Result<ChangeKind> {
        self.reject_scratch(path)?;
        let path = NormalizedPath::parse_str(path)?;
        let mut state = self.state.write().map_err(lock_error)?;
        let kind = state.replace_file(path, bytes)?;
        state.rebuild_changes();
        Ok(kind)
    }

    #[cfg_attr(windows, allow(dead_code))]
    pub fn write(&self, path: &str, offset: u64, data: &[u8]) -> Result<ChangeKind> {
        self.reject_scratch(path)?;
        let path = NormalizedPath::parse_str(path)?;
        let mut state = self.state.write().map_err(lock_error)?;
        let mut bytes = state
            .files
            .get(path.as_str())
            .map(|file| file.bytes.to_vec())
            .unwrap_or_default();
        let offset = usize::try_from(offset).context("write offset exceeds address space")?;
        if bytes.len() < offset {
            bytes.resize(offset, 0);
        }
        let end = offset
            .checked_add(data.len())
            .context("write length overflow")?;
        if bytes.len() < end {
            bytes.resize(end, 0);
        }
        bytes[offset..end].copy_from_slice(data);
        let kind = state.replace_file(path, bytes)?;
        state.rebuild_changes();
        Ok(kind)
    }

    #[cfg_attr(windows, allow(dead_code))]
    pub fn resize(&self, path: &str, size: u64) -> Result<ChangeKind> {
        self.reject_scratch(path)?;
        let path = NormalizedPath::parse_str(path)?;
        let mut state = self.state.write().map_err(lock_error)?;
        let mut bytes = state
            .files
            .get(path.as_str())
            .map(|file| file.bytes.to_vec())
            .unwrap_or_default();
        bytes.resize(
            usize::try_from(size).context("file size exceeds address space")?,
            0,
        );
        let kind = state.replace_file(path, bytes)?;
        state.rebuild_changes();
        Ok(kind)
    }

    pub fn remove(&self, path: &str) -> Result<()> {
        if self.scratch.matches(path) {
            return Ok(());
        }
        let path = NormalizedPath::parse_str(path)?;
        let mut state = self.state.write().map_err(lock_error)?;
        state.remove_path(&path);
        Ok(())
    }

    pub fn rename(&self, source: &str, destination: &str) -> Result<()> {
        self.reject_scratch(source)?;
        self.reject_scratch(destination)?;
        let source = NormalizedPath::parse_str(source)?;
        let destination = NormalizedPath::parse_str(destination)?;
        let mut state = self.state.write().map_err(lock_error)?;
        state.rename_path(&source, &destination)
    }

    pub fn changes(&self) -> Vec<Change> {
        self.state
            .read()
            .map(|state| state.changes.values().cloned().collect())
            .unwrap_or_default()
    }

    pub fn mark_checkpointed(&self, paths: &[String]) -> Result<()> {
        let mut state = self.state.write().map_err(lock_error)?;
        for path in paths {
            let path = NormalizedPath::parse_str(path)?;
            if let Some(file) = state.files.get(path.as_str()).cloned() {
                state.baseline.insert(
                    path.clone(),
                    FileRecord {
                        path,
                        hash: file.hash,
                        size: file.bytes.len() as u64,
                        source: RecordSource::Resident,
                    },
                );
            } else if state.directories.contains(path.as_str()) {
                state.baseline.insert(
                    path.clone(),
                    FileRecord {
                        path,
                        hash: String::new(),
                        size: 0,
                        source: RecordSource::Directory,
                    },
                );
            } else {
                state.baseline.remove(path.as_str());
            }
        }
        state.rebuild_changes();
        Ok(())
    }

    fn reject_scratch(&self, path: &str) -> Result<()> {
        if self.scratch.matches(path) {
            bail!("scratch content cannot enter the resident workspace: {path}");
        }
        Ok(())
    }
}
