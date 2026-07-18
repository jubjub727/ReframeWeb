impl Daemon {
    #[cfg(any(windows, unix))]
    fn mount(&mut self, session_id: &str) -> Result<serde_json::Value> {
        if self.mounts.contains_key(session_id) {
            bail!("workspace is already mounted");
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
    fn mount(&mut self, _session_id: &str) -> Result<serde_json::Value> {
        bail!("platform adapter is unavailable")
    }

    fn unmount(&mut self, session_id: &str) -> Result<serde_json::Value> {
        if !self.mounts.contains_key(session_id) {
            bail!("workspace is not mounted");
        }
        self.sync_resident_journal(session_id)?;
        #[cfg(windows)]
        if let Some(provider) = self.mounts.get_mut(session_id) {
            provider.clear_cached_tree()?;
        }
        self.mounts.remove(session_id);
        Ok(json!({"session_id":session_id,"mounted":false}))
    }

    fn destroy(&mut self, session_id: &str) -> Result<serde_json::Value> {
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
            provider.clear_cached_tree()?;
            drop(provider);
        }
        session::destroy_ephemeral(&self.store, session_id)?;
        self.residents.remove(session_id);
        Ok(json!({"session_id":session_id,"destroyed":true}))
    }

    fn sync_resident_journal(&mut self, session_id: &str) -> Result<()> {
        if let Some(resident) = self.residents.get(session_id) {
            session::replace_journal(&mut self.store, session_id, &resident.changes())?;
        }
        Ok(())
    }
}
