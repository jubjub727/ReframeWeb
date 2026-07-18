use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::mpsc;
use std::thread;

use anyhow::{Context, Result, bail};

use crate::model::{FileRecord, RecordSource};
use crate::paths::NormalizedPath;
use crate::resident::ContentCache;
use crate::store::VerifiedBlob;

const MIN_PARALLEL_FILES: usize = 16;
const MAX_SOURCE_SCAN_WORKERS: usize = 16;

pub(super) struct PendingSourceFile {
    path: NormalizedPath,
    native_path: PathBuf,
}

impl PendingSourceFile {
    pub(super) fn new(path: NormalizedPath, native_path: PathBuf) -> Self {
        Self { path, native_path }
    }
}

pub(super) fn read_source_files(
    files: &[PendingSourceFile],
    cache: Option<&ContentCache>,
) -> Result<Vec<FileRecord>> {
    if files.len() < MIN_PARALLEL_FILES {
        return files
            .iter()
            .map(|file| read_source_file(file, cache))
            .collect();
    }
    ordered_parallel_map(files, source_scan_worker_count(files.len()), |file| {
        read_source_file(file, cache)
    })
}

fn read_source_file(file: &PendingSourceFile, cache: Option<&ContentCache>) -> Result<FileRecord> {
    let bytes = fs::read(&file.native_path)
        .with_context(|| format!("read memory source file {}", file.native_path.display()))?;
    let size = bytes.len() as u64;
    let blob = VerifiedBlob::new(bytes.into());
    let hash = blob.hash_hex();
    if let Some(cache) = cache {
        cache.insert(blob);
    }
    Ok(FileRecord {
        path: file.path.clone(),
        hash,
        size,
        source: RecordSource::Overlay,
    })
}

fn source_scan_worker_count(file_count: usize) -> usize {
    if file_count == 0 {
        return 0;
    }
    let available = thread::available_parallelism().map_or(1, usize::from);
    available
        .saturating_mul(2)
        .min(MAX_SOURCE_SCAN_WORKERS)
        .min(file_count)
        .max(1)
}

fn ordered_parallel_map<T, U, F>(items: &[T], worker_count: usize, operation: F) -> Result<Vec<U>>
where
    T: Sync,
    U: Send,
    F: Fn(&T) -> Result<U> + Sync,
{
    if items.is_empty() {
        return Ok(Vec::new());
    }
    let worker_count = worker_count.clamp(1, items.len());
    let next = AtomicUsize::new(0);
    let (sender, receiver) = mpsc::sync_channel(worker_count);

    let mut indexed = thread::scope(|scope| -> Result<Vec<(usize, Result<U>)>> {
        let mut workers = Vec::with_capacity(worker_count);
        for _ in 0..worker_count {
            let sender = sender.clone();
            let operation = &operation;
            let next = &next;
            workers.push(scope.spawn(move || {
                loop {
                    let index = next.fetch_add(1, Ordering::Relaxed);
                    let Some(item) = items.get(index) else {
                        break;
                    };
                    if sender.send((index, operation(item))).is_err() {
                        break;
                    }
                }
            }));
        }
        drop(sender);

        let indexed = receiver.into_iter().collect::<Vec<_>>();
        let mut panicked = false;
        for worker in workers {
            panicked |= worker.join().is_err();
        }
        if panicked {
            bail!("memory source scan worker panicked");
        }
        Ok(indexed)
    })?;

    if indexed.len() != items.len() {
        bail!("memory source scan produced an incomplete result");
    }
    indexed.sort_unstable_by_key(|(index, _)| *index);
    indexed.into_iter().map(|(_, result)| result).collect()
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::time::Duration;

    use anyhow::anyhow;

    use super::*;

    #[test]
    fn parallel_map_preserves_input_order_and_bounds_concurrency() -> Result<()> {
        let items = (0..32).collect::<Vec<_>>();
        let active = AtomicUsize::new(0);
        let maximum = AtomicUsize::new(0);
        let output = ordered_parallel_map(&items, 4, |item| {
            let now = active.fetch_add(1, Ordering::SeqCst) + 1;
            maximum.fetch_max(now, Ordering::SeqCst);
            thread::sleep(Duration::from_millis((31 - item) as u64));
            active.fetch_sub(1, Ordering::SeqCst);
            Ok(*item)
        })?;

        assert_eq!(output, items);
        assert!(maximum.load(Ordering::SeqCst) <= 4);
        Ok(())
    }

    #[test]
    fn parallel_map_returns_the_first_error_in_input_order() {
        let error = ordered_parallel_map(&[0, 1, 2, 3], 4, |item| {
            if *item == 1 {
                thread::sleep(Duration::from_millis(10));
                Err(anyhow!("first"))
            } else if *item == 3 {
                Err(anyhow!("later"))
            } else {
                Ok(*item)
            }
        })
        .unwrap_err();

        assert_eq!(error.to_string(), "first");
    }

    #[test]
    fn worker_count_is_bounded_by_files_and_the_hard_limit() {
        assert_eq!(source_scan_worker_count(0), 0);
        assert_eq!(source_scan_worker_count(1), 1);
        assert!(source_scan_worker_count(usize::MAX) <= MAX_SOURCE_SCAN_WORKERS);
    }
}
