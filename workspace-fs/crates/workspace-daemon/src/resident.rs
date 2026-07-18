mod mutations;
mod state;
mod storage;

#[cfg(test)]
mod tests;

use std::collections::{BTreeMap, BTreeSet};
use std::sync::{Arc, RwLock};

use anyhow::Result;

use crate::model::{Change, FileRecord, RecordSource};
use crate::paths::{NormalizedPath, ScratchMatcher};
use crate::session;
use crate::store::Store;

use self::storage::{load_record, validate_content};

#[derive(Clone)]
pub struct ResidentFile {
    pub bytes: Arc<[u8]>,
    pub hash: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ResidentStats {
    pub files: usize,
    pub bytes: u64,
}

#[derive(Default)]
struct ResidentState {
    baseline: BTreeMap<NormalizedPath, FileRecord>,
    files: BTreeMap<NormalizedPath, ResidentFile>,
    directories: BTreeSet<NormalizedPath>,
    changes: BTreeMap<NormalizedPath, Change>,
}

pub struct ResidentWorkspace {
    state: RwLock<ResidentState>,
    scratch: ScratchMatcher,
}

impl ResidentWorkspace {
    pub fn load(store: &Store, session_id: &str) -> Result<Arc<Self>> {
        let mut baseline = session::baseline(store, session_id)?;
        baseline.retain(|_, record| record.source != RecordSource::Tombstone);
        let mut by_hash: BTreeMap<String, Arc<[u8]>> = BTreeMap::new();
        let mut files = BTreeMap::new();
        let mut directories = BTreeSet::new();
        for (path, record) in &baseline {
            if record.source == RecordSource::Directory {
                add_parent_directories(&mut directories, path.as_str())?;
                directories.insert(path.clone());
                continue;
            }
            add_parent_directories(&mut directories, path.as_str())?;
            let bytes = if let Some(bytes) = by_hash.get(&record.hash) {
                Arc::clone(bytes)
            } else {
                let bytes: Arc<[u8]> = load_record(store, record)?.into();
                validate_content(record, &bytes)?;
                by_hash.insert(record.hash.clone(), Arc::clone(&bytes));
                bytes
            };
            files.insert(
                path.clone(),
                ResidentFile {
                    bytes,
                    hash: record.hash.clone(),
                },
            );
        }
        Ok(Arc::new(Self {
            state: RwLock::new(ResidentState {
                baseline,
                files,
                directories,
                changes: BTreeMap::new(),
            }),
            scratch: session::scratch_matcher(store, session_id)?,
        }))
    }

    pub fn file(&self, path: &str) -> Option<ResidentFile> {
        self.state.read().ok()?.files.get(path).cloned()
    }

    #[cfg_attr(windows, allow(dead_code))]
    pub fn contains_file(&self, path: &str) -> bool {
        self.state
            .read()
            .map(|state| state.files.contains_key(path))
            .unwrap_or(false)
    }

    pub fn contains_path(&self, path: &str) -> bool {
        if path.is_empty() {
            return true;
        }
        let Ok(state) = self.state.read() else {
            return false;
        };
        state.directories.contains(path)
            || state.files.contains_key(path)
            || state
                .files
                .keys()
                .any(|candidate| has_prefix(candidate.as_str(), path))
    }

    #[cfg_attr(windows, allow(dead_code))]
    pub fn is_scratch(&self, path: &str) -> bool {
        self.scratch.matches(path)
    }

    pub fn entries(&self, directory: &str) -> Vec<(String, bool, u64)> {
        let prefix = if directory.is_empty() {
            String::new()
        } else {
            format!("{directory}/")
        };
        let Ok(state) = self.state.read() else {
            return Vec::new();
        };
        let mut entries = BTreeMap::new();
        for path in &state.directories {
            add_directory_entry(&mut entries, path.as_str(), &prefix);
        }
        for (path, file) in &state.files {
            let Some(remainder) = path.as_str().strip_prefix(&prefix) else {
                continue;
            };
            let mut parts = remainder.splitn(2, '/');
            let name = parts.next().unwrap_or_default();
            if name.is_empty() {
                continue;
            }
            let is_directory = parts.next().is_some();
            entries.entry(name.to_owned()).or_insert((
                name.to_owned(),
                is_directory,
                if is_directory {
                    0
                } else {
                    file.bytes.len() as u64
                },
            ));
        }
        entries.into_values().collect()
    }

    pub fn stats(&self) -> ResidentStats {
        let Ok(state) = self.state.read() else {
            return ResidentStats { files: 0, bytes: 0 };
        };
        ResidentStats {
            files: state.files.len(),
            bytes: state
                .files
                .values()
                .map(|file| file.bytes.len() as u64)
                .sum(),
        }
    }
}

fn add_directory_entry(
    entries: &mut BTreeMap<String, (String, bool, u64)>,
    path: &str,
    prefix: &str,
) {
    let Some(remainder) = path.strip_prefix(prefix) else {
        return;
    };
    let name = remainder.split('/').next().unwrap_or_default();
    if !name.is_empty() {
        entries.insert(name.to_owned(), (name.to_owned(), true, 0));
    }
}

fn add_parent_directories(directories: &mut BTreeSet<NormalizedPath>, path: &str) -> Result<()> {
    let mut current = String::new();
    let mut parts = path.split('/').peekable();
    while let Some(part) = parts.next() {
        if parts.peek().is_none() {
            break;
        }
        if !current.is_empty() {
            current.push('/');
        }
        current.push_str(part);
        directories.insert(NormalizedPath::parse_str(&current)?);
    }
    Ok(())
}

fn has_prefix(candidate: &str, prefix: &str) -> bool {
    candidate
        .strip_prefix(prefix)
        .is_some_and(|suffix| suffix.starts_with('/'))
}

fn lock_error<T>(_error: std::sync::PoisonError<T>) -> anyhow::Error {
    anyhow::anyhow!("resident workspace lock was poisoned")
}
