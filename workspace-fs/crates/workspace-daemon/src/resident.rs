mod cache;
mod file;
mod index;
mod loading;
mod mutations;
mod state;
mod storage;

#[cfg(test)]
#[path = "resident/loading_tests.rs"]
mod loading_tests;
#[cfg(test)]
#[path = "resident/performance_tests.rs"]
mod performance_tests;
#[cfg(test)]
mod tests;

use std::collections::{BTreeMap, HashMap, HashSet};
use std::ops::Bound::{Excluded, Unbounded};
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::{Arc, RwLock};

use anyhow::Result;

use crate::model::FileRecord;
use crate::paths::{NormalizedPath, ScratchMatcher};
use crate::session;
use crate::store::Store;

pub use self::file::ResidentFile;
pub(crate) use self::mutations::RenameOutcome;
use crate::store::VerifiedBlob;
pub(crate) use cache::ContentCache;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ResidentStats {
    pub files: usize,
    pub bytes: u64,
}

#[derive(Clone, Default)]
struct ResidentState {
    baseline: BTreeMap<NormalizedPath, FileRecord>,
    files: HashMap<NormalizedPath, ResidentFile>,
    directories: HashSet<NormalizedPath>,
    baseline_directories: HashSet<NormalizedPath>,
    children: HashMap<String, BTreeMap<String, index::ChildEntry>>,
    dirty: HashSet<NormalizedPath>,
}

pub struct ResidentWorkspace {
    state: RwLock<ResidentState>,
    scratch: ScratchMatcher,
    file_count: AtomicUsize,
    byte_count: AtomicU64,
}

impl ResidentWorkspace {
    #[cfg(test)]
    pub fn load(store: &Store, session_id: &str) -> Result<Arc<Self>> {
        Self::load_cached(store, session_id, &ContentCache::new(0))
    }

    pub(crate) fn load_cached(
        store: &Store,
        session_id: &str,
        cache: &ContentCache,
    ) -> Result<Arc<Self>> {
        let mut baseline = session::baseline(store, session_id)?;
        baseline.retain(|_, record| record.source != crate::model::RecordSource::Tombstone);
        let scratch = session::scratch_matcher(store, session_id)?;
        let memory_roots = storage::resolve_memory_roots(store, baseline.values())?;
        let mut by_hash: HashMap<String, VerifiedBlob> = HashMap::new();
        let mut directories = HashSet::new();
        let mut queued_hashes = HashSet::new();
        let mut cold_loads = Vec::new();
        for (path, record) in &baseline {
            if record.source == crate::model::RecordSource::Directory {
                add_parent_directories(&mut directories, path.as_str())?;
                directories.insert(path.clone());
                continue;
            }
            add_parent_directories(&mut directories, path.as_str())?;
            if by_hash.contains_key(&record.hash) || !queued_hashes.insert(record.hash.clone()) {
                continue;
            }
            if let Some(blob) = cache.get(&record.hash) {
                by_hash.insert(record.hash.clone(), blob.clone());
            } else {
                cold_loads.push(storage::prepare_record_load(
                    store.root(),
                    record,
                    &memory_roots,
                )?);
            }
        }
        for (load, blob) in cold_loads.iter().zip(loading::load_records(&cold_loads)?) {
            by_hash.insert(load.expected_hash().to_owned(), cache.insert(blob));
        }

        let mut files = HashMap::with_capacity(
            baseline
                .values()
                .filter(|record| record.source != crate::model::RecordSource::Directory)
                .count(),
        );
        for (path, record) in &baseline {
            if record.source == crate::model::RecordSource::Directory {
                continue;
            }
            let blob = by_hash
                .get(&record.hash)
                .ok_or_else(|| anyhow::anyhow!("resident content was not loaded: {path}"))?;
            files.insert(path.clone(), ResidentFile::shared(blob.clone()));
        }
        let baseline_directories = index::baseline_directories(&baseline)?;
        let children = index::build_children(&files, &directories);
        let byte_count = files.values().map(ResidentFile::len).sum::<usize>() as u64;
        let file_count = files.len();
        Ok(Arc::new(Self {
            state: RwLock::new(ResidentState {
                baseline,
                files,
                directories,
                baseline_directories,
                children,
                dirty: HashSet::new(),
            }),
            scratch,
            file_count: AtomicUsize::new(file_count),
            byte_count: AtomicU64::new(byte_count),
        }))
    }

    pub(crate) fn refresh_policy(&self, store: &Store, session_id: &str) -> Result<Arc<Self>> {
        let scratch = session::scratch_matcher(store, session_id)?;
        let state = self.state.read().map_err(lock_error)?.clone();
        Ok(Arc::new(Self {
            state: RwLock::new(state),
            scratch,
            file_count: AtomicUsize::new(self.file_count.load(Ordering::Relaxed)),
            byte_count: AtomicU64::new(self.byte_count.load(Ordering::Relaxed)),
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
        state.directories.contains(path) || state.files.contains_key(path)
    }

    #[cfg_attr(windows, allow(dead_code))]
    pub fn is_scratch(&self, path: &str) -> bool {
        self.scratch.matches(path)
    }

    pub fn entries(&self, directory: &str) -> Vec<(String, bool, u64)> {
        let Ok(state) = self.state.read() else {
            return Vec::new();
        };
        state
            .children
            .get(directory)
            .map(|entries| {
                entries
                    .iter()
                    .map(|(name, entry)| {
                        (
                            name.clone(),
                            entry.is_directory(),
                            entry.file().map_or(0, |file| file.len() as u64),
                        )
                    })
                    .collect()
            })
            .unwrap_or_default()
    }

    /// Visits indexed children strictly after `marker` and stops as soon as
    /// the visitor returns false. This lets paged filesystem callbacks avoid
    /// rebuilding the full directory for every continuation request.
    pub fn visit_entries_after(
        &self,
        directory: &str,
        marker: Option<&str>,
        mut visitor: impl FnMut(&str, bool, u64) -> bool,
    ) -> Result<bool> {
        let state = self.state.read().map_err(lock_error)?;
        let Some(entries) = state.children.get(directory) else {
            return Ok(true);
        };
        if let Some(marker) = marker {
            for (name, entry) in entries.range((Excluded(marker.to_owned()), Unbounded)) {
                let size = entry.file().map_or(0, |file| file.len() as u64);
                if !visitor(name, entry.is_directory(), size) {
                    return Ok(false);
                }
            }
        } else {
            for (name, entry) in entries {
                let size = entry.file().map_or(0, |file| file.len() as u64);
                if !visitor(name, entry.is_directory(), size) {
                    return Ok(false);
                }
            }
        }
        Ok(true)
    }

    pub fn stats(&self) -> ResidentStats {
        ResidentStats {
            files: self.file_count.load(Ordering::Relaxed),
            bytes: self.byte_count.load(Ordering::Relaxed),
        }
    }

    fn update_byte_count(&self, previous: usize, current: usize) {
        if current >= previous {
            self.byte_count
                .fetch_add((current - previous) as u64, Ordering::Relaxed);
        } else {
            self.byte_count
                .fetch_sub((previous - current) as u64, Ordering::Relaxed);
        }
    }

    fn replace_stats(&self, files: usize, bytes: u64) {
        self.file_count.store(files, Ordering::Relaxed);
        self.byte_count.store(bytes, Ordering::Relaxed);
    }

    fn subtract_stats(&self, files: usize, bytes: u64) {
        if files != 0 {
            self.file_count.fetch_sub(files, Ordering::Relaxed);
        }
        if bytes != 0 {
            self.byte_count.fetch_sub(bytes, Ordering::Relaxed);
        }
    }

    #[cfg(test)]
    pub(crate) fn empty_for_test() -> Arc<Self> {
        Arc::new(Self {
            state: RwLock::new(ResidentState::default()),
            scratch: ScratchMatcher::compile(std::iter::empty::<&str>())
                .expect("empty scratch matcher"),
            file_count: AtomicUsize::new(0),
            byte_count: AtomicU64::new(0),
        })
    }
}

fn add_parent_directories(directories: &mut HashSet<NormalizedPath>, path: &str) -> Result<()> {
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
