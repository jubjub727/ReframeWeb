use std::sync::Mutex;
use std::sync::atomic::{AtomicUsize, Ordering};

use anyhow::{Result, anyhow, bail};

use super::storage::PreparedRecordLoad;
use crate::store::VerifiedBlob;

pub(super) const MAX_COLD_LOAD_WORKERS: usize = 16;

pub(super) fn load_records(loads: &[PreparedRecordLoad]) -> Result<Vec<VerifiedBlob>> {
    let available = std::thread::available_parallelism()
        .map(usize::from)
        .unwrap_or(1);
    parallel_map_ordered(loads, worker_count(loads.len(), available), |load| {
        load.load_verified()
    })
}

pub(super) fn worker_count(item_count: usize, available: usize) -> usize {
    item_count.min(available.clamp(1, MAX_COLD_LOAD_WORKERS))
}

pub(super) fn parallel_map_ordered<T, U>(
    items: &[T],
    workers: usize,
    load: impl Fn(&T) -> Result<U> + Sync,
) -> Result<Vec<U>>
where
    T: Sync,
    U: Send,
{
    if items.is_empty() {
        return Ok(Vec::new());
    }
    if workers <= 1 {
        return items.iter().map(load).collect();
    }

    let next = AtomicUsize::new(0);
    let completed = Mutex::new(Vec::with_capacity(items.len()));
    std::thread::scope(|scope| -> Result<()> {
        let load = &load;
        let mut handles = Vec::with_capacity(workers);
        for _ in 0..workers {
            handles.push(scope.spawn(|| {
                loop {
                    let index = next.fetch_add(1, Ordering::Relaxed);
                    let Some(item) = items.get(index) else {
                        break;
                    };
                    let result = load(item);
                    let Ok(mut completed) = completed.lock() else {
                        break;
                    };
                    completed.push((index, result));
                }
            }));
        }
        for handle in handles {
            handle
                .join()
                .map_err(|_| anyhow!("resident cold-load worker panicked"))?;
        }
        Ok(())
    })?;

    let mut completed = completed
        .into_inner()
        .map_err(|_| anyhow!("resident cold-load result lock was poisoned"))?;
    if completed.len() != items.len() {
        bail!("resident cold-load worker stopped before completing its queue");
    }
    completed.sort_unstable_by_key(|(index, _)| *index);
    completed.into_iter().map(|(_, result)| result).collect()
}
