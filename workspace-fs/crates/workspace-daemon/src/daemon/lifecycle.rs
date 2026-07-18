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
                "resident_files":stats.files,
                "resident_bytes":stats.bytes
            }));
        }
        let resident = match self.residents.get(session_id) {
            Some(resident) => Arc::clone(resident),
            None => {
                let resident = ResidentWorkspace::load(&self.store, session_id)?;
                self.residents
                    .insert(session_id.to_owned(), Arc::clone(&resident));
                resident
            }
        };
        let stats = resident.stats();
        let provider = Provider::start(&self.store, session_id, resident)?;
        let worktree = provider.worktree.to_string_lossy().into_owned();
        self.mounts.insert(session_id.into(), provider);
        Ok(json!({
            "session_id":session_id,
            "mount_path":worktree,
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
        #[cfg(windows)]
        {
            let resident = self
                .residents
                .get(session_id)
                .cloned()
                .unwrap_or(ResidentWorkspace::load(&self.store, session_id)?);
            let mut provider = Provider::start(&self.store, session_id, resident)?;
            provider.unmount()?;
        }
        session::destroy_ephemeral(&self.store, session_id)?;
        self.residents.remove(session_id);
        Ok(json!({"session_id":session_id,"destroyed":true}))
    }

    pub(super) fn sync_resident_journal(&mut self, session_id: &str) -> Result<()> {
        if let Some(resident) = self.residents.get(session_id) {
            session::replace_journal(&mut self.store, session_id, &resident.changes())?;
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

    use anyhow::{Result, bail};

    use super::{prepare_mount_slot, retain_until_unmounted};

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
