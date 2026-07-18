use std::collections::HashMap;
use std::hash::Hash;
use std::sync::Arc;

use anyhow::{Context, Result, bail};
use serde_json::json;

use crate::resident::ResidentWorkspace;
use crate::session;

use super::Daemon;
#[cfg(any(windows, unix))]
use super::Provider;

impl Daemon {
    #[cfg(any(windows, unix))]
    pub(super) fn mount(&mut self, session_id: &str) -> Result<serde_json::Value> {
        let key = session_id.to_owned();
        if prepare_mount_slot(
            &mut self.mounts,
            &key,
            Provider::is_mounted,
            Provider::unmount,
        )? {
            let provider = self
                .mounts
                .get(session_id)
                .context("mounted workspace provider disappeared")?;
            let stats = self
                .residents
                .get(session_id)
                .context("mounted workspace has no resident content store")?
                .stats();
            return Ok(json!({
                "session_id":session_id,
                "mount_path":provider.worktree.to_string_lossy(),
                "backend":provider.backend_name(),
                "resident_files":stats.files,
                "resident_bytes":stats.bytes
            }));
        }
        let resident = match self.residents.get(session_id) {
            Some(resident) => Arc::clone(resident),
            None => {
                let resident =
                    ResidentWorkspace::load_cached(&self.store, session_id, &self.content_cache)?;
                self.residents
                    .insert(session_id.to_owned(), Arc::clone(&resident));
                resident
            }
        };
        let stats = resident.stats();
        let provider = Provider::start(&self.store, session_id, resident)?;
        let worktree = provider.worktree.to_string_lossy().into_owned();
        let backend = provider.backend_name();
        self.mounts.insert(session_id.into(), provider);
        Ok(json!({
            "session_id":session_id,
            "mount_path":worktree,
            "backend":backend,
            "resident_files":stats.files,
            "resident_bytes":stats.bytes
        }))
    }

    #[cfg(not(any(windows, unix)))]
    pub(super) fn mount(&mut self, _session_id: &str) -> Result<serde_json::Value> {
        bail!("platform adapter is unavailable")
    }

    pub(super) fn unmount(&mut self, session_id: &str) -> Result<serde_json::Value> {
        if !self.mounts.contains_key(session_id) {
            session::worktree(&self.store, session_id)?;
            return Ok(json!({"session_id":session_id,"mounted":false}));
        }
        self.sync_resident_journal(session_id)?;
        let key = session_id.to_owned();
        retain_until_unmounted(&mut self.mounts, &key, |provider| provider.unmount())?;
        Ok(json!({"session_id":session_id,"mounted":false}))
    }

    #[cfg(any(windows, unix))]
    pub(super) fn is_mounted(&self, session_id: &str) -> bool {
        self.mounts
            .get(session_id)
            .is_some_and(Provider::is_mounted)
    }

    #[cfg(not(any(windows, unix)))]
    pub(super) fn is_mounted(&self, _session_id: &str) -> bool {
        false
    }

    #[cfg(any(windows, unix))]
    pub(super) fn mounted_count(&self) -> usize {
        self.mounts
            .values()
            .filter(|provider| provider.is_mounted())
            .count()
    }

    #[cfg(not(any(windows, unix)))]
    pub(super) fn mounted_count(&self) -> usize {
        0
    }

    pub(super) fn destroy(&mut self, session_id: &str) -> Result<serde_json::Value> {
        if self.mounts.contains_key(session_id) {
            bail!("unmount workspace before destroying it");
        }
        // A mounted ProjFS provider clears its placeholders during unmount. If
        // the daemon previously exited without unmounting, native recursive
        // deletion can still remove the stopped virtualization root. Starting
        // a provider here only to stop it again adds driver and resident-load
        // latency and can accidentally select the unrelated WinFsp backend.
        session::destroy_ephemeral(&self.store, session_id)?;
        self.residents.remove(session_id);
        Ok(json!({"session_id":session_id,"destroyed":true}))
    }

    pub(super) fn sync_resident_journal(&mut self, session_id: &str) -> Result<()> {
        if let Some(resident) = self.residents.get(session_id) {
            session::replace_journal(&mut self.store, session_id, &resident.changes()?)?;
        }
        Ok(())
    }
}

fn prepare_mount_slot<K, P>(
    mounts: &mut HashMap<K, P>,
    key: &K,
    is_mounted: impl Fn(&P) -> bool,
    unmount: impl FnOnce(&mut P) -> Result<()>,
) -> Result<bool>
where
    K: Eq + Hash,
{
    if mounts.get(key).is_some_and(is_mounted) {
        return Ok(true);
    }
    if mounts.contains_key(key) {
        retain_until_unmounted(mounts, key, unmount)?;
    }
    Ok(false)
}

fn retain_until_unmounted<K, P>(
    mounts: &mut HashMap<K, P>,
    key: &K,
    unmount: impl FnOnce(&mut P) -> Result<()>,
) -> Result<()>
where
    K: Eq + Hash,
{
    {
        let provider = mounts
            .get_mut(key)
            .context("mounted workspace provider disappeared during unmount")?;
        unmount(provider)?;
    }
    mounts.remove(key);
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;
    use std::fs;

    use anyhow::{Result, bail};

    use crate::daemon::Daemon;
    use crate::resident::ContentCache;
    use crate::session;
    use crate::store::Store;

    use super::{prepare_mount_slot, retain_until_unmounted};

    #[test]
    fn destroying_an_unmounted_workspace_does_not_reload_resident_content() -> Result<()> {
        let root = std::env::temp_dir().join(format!(
            "reframe-destroy-unmounted-{}",
            Store::next_id("test")
        ));
        let memory = root.join("memory");
        fs::create_dir_all(&memory)?;
        fs::write(memory.join("remembered.txt"), b"content")?;
        let mut store = Store::open(&root)?;
        store.persist_memory_source("memory:destroy-test", &memory)?;
        let created = session::create(
            &mut store,
            "workspace",
            Some("workspace"),
            &["memory:destroy-test".into()],
            &[],
        )?;
        let worktree = std::path::PathBuf::from(&created.worktree);
        fs::write(worktree.join("stale-projected-file"), b"content")?;
        // Resident loading would now fail. Destroy must not read source bytes
        // merely to remove an already-unmounted workspace.
        fs::remove_dir_all(memory)?;
        let session_root = worktree
            .parent()
            .expect("created worktree has a session parent")
            .to_owned();
        let mut daemon = Daemon {
            store,
            content_cache: ContentCache::default(),
            residents: HashMap::new(),
            process_idempotency_requests: Default::default(),
            mounts: HashMap::new(),
        };

        let result = daemon.destroy("workspace")?;

        assert_eq!(result["destroyed"], true);
        assert!(!session_root.exists());
        drop(daemon);
        fs::remove_dir_all(root)?;
        Ok(())
    }

    #[test]
    fn failed_unmount_retains_provider_for_retry() -> Result<()> {
        let key = "workspace".to_owned();
        let mut mounts = HashMap::from([(key.clone(), 0_u8)]);

        let error = retain_until_unmounted(&mut mounts, &key, |attempts| {
            *attempts += 1;
            bail!("injected cleanup failure")
        });
        assert!(error.is_err());
        assert_eq!(mounts.get(&key), Some(&1));

        retain_until_unmounted(&mut mounts, &key, |attempts| {
            *attempts += 1;
            Ok(())
        })?;
        assert!(!mounts.contains_key(&key));
        Ok(())
    }

    #[test]
    fn inactive_provider_is_cleaned_before_a_new_mount() -> Result<()> {
        let key = "workspace".to_owned();
        let mut mounts = HashMap::from([(key.clone(), false)]);

        let error = prepare_mount_slot(
            &mut mounts,
            &key,
            |mounted| *mounted,
            |_| bail!("injected scratch cleanup failure"),
        );
        assert!(error.is_err());
        assert!(mounts.contains_key(&key));

        let already_mounted =
            prepare_mount_slot(&mut mounts, &key, |mounted| *mounted, |_| Ok(()))?;
        assert!(!already_mounted);
        assert!(!mounts.contains_key(&key));
        Ok(())
    }
}
