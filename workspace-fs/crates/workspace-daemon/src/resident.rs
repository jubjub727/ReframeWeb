use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;
use std::sync::{Arc, RwLock};

use anyhow::{Context, Result, bail};

use crate::model::{Change, ChangeKind, FileRecord};
use crate::paths::{ScratchMatcher, native_path};
use crate::session;
use crate::store::Store;

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

pub struct ResidentWorkspace {
    baseline: RwLock<BTreeMap<String, FileRecord>>,
    files: RwLock<BTreeMap<String, ResidentFile>>,
    directories: RwLock<BTreeSet<String>>,
    deleted: RwLock<BTreeSet<String>>,
    scratch: ScratchMatcher,
}

impl ResidentWorkspace {
    pub fn load(store: &Store, session_id: &str) -> Result<Arc<Self>> {
        let mut baseline = session::baseline(store, session_id)?;
        baseline.retain(|_, record| record.source_kind != "tombstone");
        let mut by_hash: BTreeMap<String, Arc<[u8]>> = BTreeMap::new();
        let mut files = BTreeMap::new();
        let mut directories = BTreeSet::new();
        for (path, record) in &baseline {
            if record.source_kind == "directory" {
                add_parent_directories(&mut directories, path);
                directories.insert(path.clone());
                continue;
            }
            add_parent_directories(&mut directories, path);
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
            baseline: RwLock::new(baseline),
            files: RwLock::new(files),
            directories: RwLock::new(directories),
            deleted: RwLock::new(BTreeSet::new()),
            scratch: session::scratch_matcher(store, session_id)?,
        }))
    }

    pub fn file(&self, path: &str) -> Option<ResidentFile> {
        self.files.read().ok()?.get(path).cloned()
    }

    #[cfg_attr(windows, allow(dead_code))]
    pub fn contains_file(&self, path: &str) -> bool {
        self.files
            .read()
            .map(|files| files.contains_key(path))
            .unwrap_or(false)
    }

    pub fn contains_path(&self, path: &str) -> bool {
        if path.is_empty()
            || self
                .directories
                .read()
                .map(|directories| directories.contains(path))
                .unwrap_or(false)
        {
            return true;
        }
        let Ok(files) = self.files.read() else {
            return false;
        };
        files.contains_key(path)
            || files
                .keys()
                .any(|candidate| candidate.starts_with(&format!("{path}/")))
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
        let Ok(files) = self.files.read() else {
            return Vec::new();
        };
        let mut entries = BTreeMap::new();
        if let Ok(directories) = self.directories.read() {
            for path in directories.iter() {
                let Some(remainder) = path.strip_prefix(&prefix) else {
                    continue;
                };
                let name = remainder.split('/').next().unwrap_or_default();
                if !name.is_empty() {
                    entries.insert(name.to_owned(), (name.to_owned(), true, 0));
                }
            }
        }
        for (path, file) in files.iter() {
            let Some(remainder) = path.strip_prefix(&prefix) else {
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
        let Ok(files) = self.files.read() else {
            return ResidentStats { files: 0, bytes: 0 };
        };
        ResidentStats {
            files: files.len(),
            bytes: files.values().map(|file| file.bytes.len() as u64).sum(),
        }
    }
}

include!("resident/mutations.rs");
include!("resident/storage.rs");
include!("resident/tests.rs");
