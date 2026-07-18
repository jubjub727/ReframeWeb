use std::collections::{HashMap, VecDeque};
use std::sync::Mutex;

use crate::store::VerifiedBlob;

const DEFAULT_CACHE_BYTES: usize = 512 * 1024 * 1024;
const CACHE_BYTES_ENV: &str = "REFRAME_WORKSPACE_RAM_CACHE_BYTES";
const RECENCY_GENERATIONS_PER_ENTRY: usize = 4;
const RECENCY_GENERATION_SLOP: usize = 64;

pub(crate) struct ContentCache {
    capacity: usize,
    state: Mutex<CacheState>,
}

pub(crate) struct ContentCachePin<'a> {
    cache: &'a ContentCache,
}

#[derive(Default)]
struct CacheState {
    entries: HashMap<String, CacheEntry>,
    recency: VecDeque<(String, u64)>,
    clock: u64,
    bytes: usize,
    pins: usize,
}

struct CacheEntry {
    blob: VerifiedBlob,
    generation: u64,
}

impl ContentCache {
    pub(crate) fn from_environment() -> Self {
        let capacity = std::env::var(CACHE_BYTES_ENV)
            .ok()
            .and_then(|value| value.parse().ok())
            .unwrap_or(DEFAULT_CACHE_BYTES);
        Self::new(capacity)
    }

    pub(crate) fn new(capacity: usize) -> Self {
        Self {
            capacity,
            state: Mutex::new(CacheState::default()),
        }
    }

    pub(crate) fn get(&self, hash: &str) -> Option<VerifiedBlob> {
        let mut state = self.state.lock().ok()?;
        let blob = state.entries.get(hash)?.blob.clone();
        state.touch(hash);
        Some(blob)
    }

    pub(crate) fn pin(&self) -> ContentCachePin<'_> {
        if let Ok(mut state) = self.state.lock() {
            state.pins = state.pins.saturating_add(1);
        }
        ContentCachePin { cache: self }
    }

    pub(crate) fn insert(&self, blob: VerifiedBlob) -> VerifiedBlob {
        let hash = blob.hash_hex();
        let Ok(mut state) = self.state.lock() else {
            return blob;
        };
        if let Some(existing) = state.entries.get(&hash).map(|entry| entry.blob.clone()) {
            state.touch(&hash);
            return existing;
        }
        let size = blob.bytes().len();
        if self.capacity == 0 || (size > self.capacity && state.pins == 0) {
            return blob;
        }
        let generation = state.tick();
        state.bytes = state.bytes.saturating_add(size);
        state.entries.insert(
            hash.clone(),
            CacheEntry {
                blob: blob.clone(),
                generation,
            },
        );
        state.recency.push_back((hash, generation));
        if state.pins == 0 {
            state.evict_to(self.capacity);
        }
        state.prune_recency();
        blob
    }

    #[cfg(test)]
    pub(crate) fn stats(&self) -> (usize, usize) {
        self.state
            .lock()
            .map(|state| (state.entries.len(), state.bytes))
            .unwrap_or_default()
    }

    #[cfg(test)]
    fn recency_len(&self) -> usize {
        self.state
            .lock()
            .map(|state| state.recency.len())
            .unwrap_or_default()
    }
}

impl Drop for ContentCachePin<'_> {
    fn drop(&mut self) {
        if let Ok(mut state) = self.cache.state.lock() {
            state.pins = state.pins.saturating_sub(1);
            if state.pins == 0 {
                state.evict_to(self.cache.capacity);
            }
        }
    }
}

impl Default for ContentCache {
    fn default() -> Self {
        Self::from_environment()
    }
}

impl CacheState {
    fn tick(&mut self) -> u64 {
        self.clock = self.clock.wrapping_add(1).max(1);
        self.clock
    }

    fn touch(&mut self, hash: &str) {
        let generation = self.tick();
        if let Some(entry) = self.entries.get_mut(hash) {
            entry.generation = generation;
            self.recency.push_back((hash.to_owned(), generation));
            self.prune_recency();
        }
    }

    fn prune_recency(&mut self) {
        let maximum = self
            .entries
            .len()
            .saturating_mul(RECENCY_GENERATIONS_PER_ENTRY)
            .saturating_add(RECENCY_GENERATION_SLOP);
        if self.recency.len() <= maximum {
            return;
        }
        let mut current = self
            .entries
            .iter()
            .map(|(hash, entry)| (hash.clone(), entry.generation))
            .collect::<Vec<_>>();
        current.sort_unstable_by_key(|(_, generation)| *generation);
        self.recency = current.into();
    }

    fn evict_to(&mut self, capacity: usize) {
        while self.bytes > capacity {
            let Some((hash, generation)) = self.recency.pop_front() else {
                break;
            };
            let current = self.entries.get(&hash).map(|entry| entry.generation);
            if current != Some(generation) {
                continue;
            }
            if let Some(entry) = self.entries.remove(&hash) {
                self.bytes = self.bytes.saturating_sub(entry.blob.bytes().len());
            }
        }
        self.prune_recency();
    }
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use super::*;

    #[test]
    fn cache_deduplicates_and_evicts_verified_content() {
        let cache = ContentCache::new(6);
        let first = VerifiedBlob::new(Arc::from(&b"one"[..]));
        let duplicate = VerifiedBlob::new(Arc::from(&b"one"[..]));
        let second = VerifiedBlob::new(Arc::from(&b"two"[..]));
        let third = VerifiedBlob::new(Arc::from(&b"tri"[..]));

        let retained = cache.insert(first.clone());
        let reused = cache.insert(duplicate);
        assert!(Arc::ptr_eq(&retained.bytes_arc(), &reused.bytes_arc()));
        cache.insert(second.clone());
        assert!(cache.get(&first.hash_hex()).is_some());
        cache.insert(third);

        assert!(cache.get(&first.hash_hex()).is_some());
        assert!(cache.get(&second.hash_hex()).is_none());
        assert_eq!(cache.stats(), (2, 6));
    }

    #[test]
    fn pin_keeps_an_oversized_creation_seed_until_resident_load() {
        let cache = ContentCache::new(3);
        let blob = VerifiedBlob::new(Arc::from(&b"larger"[..]));
        let hash = blob.hash_hex();
        {
            let _pin = cache.pin();
            cache.insert(blob);
            assert!(cache.get(&hash).is_some());
        }
        assert!(cache.get(&hash).is_none());
    }

    #[test]
    fn repeated_hits_do_not_grow_recency_history_without_eviction() {
        let cache = ContentCache::new(1024 * 1024);
        let blob = cache.insert(VerifiedBlob::new(Arc::from(&b"hot"[..])));
        let hash = blob.hash_hex();

        for _ in 0..10_000 {
            assert!(cache.get(&hash).is_some());
        }

        assert_eq!(cache.stats(), (1, 3));
        assert!(cache.recency_len() <= RECENCY_GENERATIONS_PER_ENTRY + RECENCY_GENERATION_SLOP);
    }
}
