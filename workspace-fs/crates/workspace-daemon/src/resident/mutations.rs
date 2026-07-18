use anyhow::{Context, Result, bail};

use crate::model::{Change, ChangeKind, FileRecord, RecordSource};
use crate::paths::NormalizedPath;

use super::{ResidentFile, ResidentWorkspace, index, lock_error};

#[derive(Default)]
pub(crate) struct RenameOutcome {
    pub(crate) replaced_file: Option<ResidentFile>,
    pub(crate) replaced_directory: bool,
}

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
        let inserted_parents = state.ensure_parent_directories(path.as_str())?;
        state.dirty.extend(inserted_parents);
        if state.directories.insert(path.clone()) {
            index::insert_directory(&mut state.children, path.as_str());
            state.dirty.insert(path);
        }
        Ok(())
    }

    pub fn replace(&self, path: &str, bytes: Vec<u8>) -> Result<ChangeKind> {
        self.reject_scratch(path)?;
        let path = NormalizedPath::parse_str(path)?;
        let mut state = self.state.write().map_err(lock_error)?;
        let (kind, previous, current, inserted) = state.replace_file(path, bytes)?;
        if inserted {
            self.file_count
                .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        }
        self.update_byte_count(previous, current);
        drop(state);
        Ok(kind)
    }

    #[cfg_attr(windows, allow(dead_code))]
    pub fn write(&self, path: &str, offset: u64, data: &[u8]) -> Result<ChangeKind> {
        self.reject_scratch(path)?;
        let path = NormalizedPath::parse_str(path)?;
        let state = self.state.read().map_err(lock_error)?;
        let Some(file) = state.files.get(path.as_str()).cloned() else {
            drop(state);
            let offset = usize::try_from(offset).context("write offset exceeds address space")?;
            let end = offset
                .checked_add(data.len())
                .context("write length overflow")?;
            let mut bytes = vec![0; end];
            bytes[offset..].copy_from_slice(data);
            return self.replace(path.as_str(), bytes);
        };
        let kind = if state.baseline.contains_key(path.as_str()) {
            ChangeKind::Write
        } else {
            ChangeKind::Create
        };
        let (previous, current) = file.write(offset, data)?;
        self.update_byte_count(previous, current);
        drop(state);
        if file.mark_dirty() {
            self.state.write().map_err(lock_error)?.dirty.insert(path);
        }
        Ok(kind)
    }

    pub(crate) fn write_open_file(
        &self,
        path_hint: &str,
        file: &ResidentFile,
        offset: u64,
        data: &[u8],
    ) -> Result<()> {
        let state = self.state.read().map_err(lock_error)?;
        let Some(path) = linked_file_path(&state.files, path_hint, file) else {
            drop(state);
            file.write(offset, data)?;
            return Ok(());
        };
        let (previous, current) = file.write(offset, data)?;
        self.update_byte_count(previous, current);
        drop(state);
        if file.mark_dirty() {
            self.state.write().map_err(lock_error)?.dirty.insert(path);
        }
        Ok(())
    }

    #[cfg_attr(windows, allow(dead_code))]
    pub fn resize(&self, path: &str, size: u64) -> Result<ChangeKind> {
        self.reject_scratch(path)?;
        let path = NormalizedPath::parse_str(path)?;
        let state = self.state.read().map_err(lock_error)?;
        let Some(file) = state.files.get(path.as_str()).cloned() else {
            drop(state);
            return self.replace(
                path.as_str(),
                vec![0; usize::try_from(size).context("file size exceeds address space")?],
            );
        };
        let kind = if state.baseline.contains_key(path.as_str()) {
            ChangeKind::Write
        } else {
            ChangeKind::Create
        };
        let (previous, current) = file.resize(size)?;
        self.update_byte_count(previous, current);
        drop(state);
        if file.mark_dirty() {
            self.state.write().map_err(lock_error)?.dirty.insert(path);
        }
        Ok(kind)
    }

    pub(crate) fn resize_open_file(
        &self,
        path_hint: &str,
        file: &ResidentFile,
        size: u64,
    ) -> Result<()> {
        let state = self.state.read().map_err(lock_error)?;
        let Some(path) = linked_file_path(&state.files, path_hint, file) else {
            drop(state);
            file.resize(size)?;
            return Ok(());
        };
        let (previous, current) = file.resize(size)?;
        self.update_byte_count(previous, current);
        drop(state);
        if file.mark_dirty() {
            self.state.write().map_err(lock_error)?.dirty.insert(path);
        }
        Ok(())
    }

    pub(crate) fn replace_open_file(
        &self,
        path_hint: &str,
        file: &ResidentFile,
        bytes: Vec<u8>,
    ) -> Result<()> {
        let state = self.state.read().map_err(lock_error)?;
        let Some(path) = linked_file_path(&state.files, path_hint, file) else {
            drop(state);
            file.replace(bytes)?;
            return Ok(());
        };
        let (previous, current) = file.replace(bytes)?;
        self.update_byte_count(previous, current);
        drop(state);
        if file.mark_dirty() {
            self.state.write().map_err(lock_error)?.dirty.insert(path);
        }
        Ok(())
    }

    pub fn remove(&self, path: &str) -> Result<()> {
        if self.scratch.matches(path) {
            return Ok(());
        }
        let path = NormalizedPath::parse_str(path)?;
        let mut state = self.state.write().map_err(lock_error)?;
        if let Some((files, bytes)) = state.remove_path(&path) {
            self.subtract_stats(files, bytes);
        } else {
            let (files, bytes) = state_stats(&state.files);
            self.replace_stats(files, bytes);
        }
        drop(state);
        Ok(())
    }

    pub(crate) fn remove_open_file(&self, path_hint: &str, file: &ResidentFile) -> Result<bool> {
        let mut state = self.state.write().map_err(lock_error)?;
        let Some(path) = linked_file_path(&state.files, path_hint, file) else {
            return Ok(false);
        };
        let (files, bytes) = state
            .remove_path(&path)
            .expect("an identity-matched resident file uses the single-file removal path");
        self.subtract_stats(files, bytes);
        Ok(true)
    }

    pub fn rename(&self, source: &str, destination: &str) -> Result<()> {
        self.rename_with_replace(source, destination, true)
            .map(|_| ())
    }

    pub(crate) fn rename_with_replace(
        &self,
        source: &str,
        destination: &str,
        replace: bool,
    ) -> Result<RenameOutcome> {
        self.reject_scratch(source)?;
        self.reject_scratch(destination)?;
        let source = NormalizedPath::parse_str(source)?;
        let destination = NormalizedPath::parse_str(destination)?;
        let mut state = self.state.write().map_err(lock_error)?;
        let source_is_file = state.files.contains_key(source.as_str());
        let source_is_directory = state.directories.contains(source.as_str());
        if !source_is_file && !source_is_directory {
            bail!("rename source does not exist: {source}");
        }
        if source == destination {
            return Ok(RenameOutcome::default());
        }
        let destination_file = state.files.get(destination.as_str()).cloned();
        let destination_is_directory = state.directories.contains(destination.as_str());
        if (destination_file.is_some() || destination_is_directory) && !replace {
            bail!("rename destination already exists: {destination}");
        }
        if source_is_file && destination_is_directory {
            bail!("cannot rename a file over a directory: {destination}");
        }
        if source_is_directory && destination_file.is_some() {
            bail!("cannot rename a directory over a file: {destination}");
        }
        if source_is_directory
            && destination_is_directory
            && state
                .children
                .get(destination.as_str())
                .is_some_and(|children| !children.is_empty())
        {
            bail!("rename destination directory is not empty: {destination}");
        }
        let outcome = RenameOutcome {
            replaced_file: destination_file,
            replaced_directory: destination_is_directory,
        };
        if let Some((files, bytes)) = state.rename_path(&source, &destination)? {
            self.subtract_stats(files, bytes);
        } else {
            let (files, bytes) = state_stats(&state.files);
            self.replace_stats(files, bytes);
        }
        drop(state);
        Ok(outcome)
    }

    pub fn changes(&self) -> Result<Vec<Change>> {
        self.state.write().map_err(lock_error)?.collect_changes()
    }

    pub fn mark_checkpointed(&self, paths: &[String]) -> Result<()> {
        let mut state = self.state.write().map_err(lock_error)?;
        for path in paths {
            let path = NormalizedPath::parse_str(path)?;
            if let Some(file) = state.files.get(path.as_str()).cloned() {
                state.baseline.insert(
                    path.clone(),
                    FileRecord {
                        path: path.clone(),
                        hash: file.hash_hex()?,
                        size: file.len() as u64,
                        source: RecordSource::Resident,
                    },
                );
                file.mark_clean();
            } else if state.directories.contains(path.as_str()) {
                state.baseline.insert(
                    path.clone(),
                    FileRecord {
                        path: path.clone(),
                        hash: String::new(),
                        size: 0,
                        source: RecordSource::Directory,
                    },
                );
            } else {
                state.baseline.remove(path.as_str());
            }
            state.dirty.remove(path.as_str());
        }
        state.refresh_baseline_directories()?;
        Ok(())
    }

    fn reject_scratch(&self, path: &str) -> Result<()> {
        if self.scratch.matches(path) {
            bail!("scratch content cannot enter the resident workspace: {path}");
        }
        Ok(())
    }
}

fn linked_file_path(
    files: &std::collections::HashMap<NormalizedPath, ResidentFile>,
    path_hint: &str,
    file: &ResidentFile,
) -> Option<NormalizedPath> {
    files
        .get_key_value(path_hint)
        .filter(|(_, candidate)| candidate.same_identity(file))
        .map(|(path, _)| path.clone())
        .or_else(|| {
            files
                .iter()
                .find(|(_, candidate)| candidate.same_identity(file))
                .map(|(path, _)| path.clone())
        })
}

fn state_stats(
    files: &std::collections::HashMap<NormalizedPath, super::ResidentFile>,
) -> (usize, u64) {
    (
        files.len(),
        files.values().map(|file| file.len() as u64).sum(),
    )
}
