impl Daemon {
    fn execute(&mut self, operation: &Operation) -> Result<serde_json::Value> {
        match operation {
            Operation::Hello => Ok(json!({"service":"reframe-workspace-daemon"})),
            Operation::Health => {
                Ok(json!({"status":"ready","mounted_workspaces":self.mounts.len()}))
            }
            Operation::CreateWorkspace {
                name,
                session_id,
                memory_sources,
                scratch_paths,
            } => {
                for memory in memory_sources {
                    match memory.source_kind.as_str() {
                        "directory" => self.store.persist_memory_source(
                            &memory.memory_id,
                            Path::new(memory.source_path.as_deref().context(
                                "directory memory source is missing source_path",
                            )?),
                        )?,
                        "checkpoint" => self.store.persist_checkpoint_source(
                            &memory.memory_id,
                            Path::new(memory.backing_store.as_deref().context(
                                "checkpoint memory source is missing backing_store",
                            )?),
                            memory.manifest_id.as_deref().context(
                                "checkpoint memory source is missing manifest_id",
                            )?,
                        )?,
                        kind => bail!("unsupported memory source kind: {kind}"),
                    }
                }
                let memory_ids = memory_sources
                    .iter()
                    .map(|memory| memory.memory_id.clone())
                    .collect::<Vec<_>>();
                let scratch = scratch_paths.iter().map(PathBuf::from).collect::<Vec<_>>();
                Ok(serde_json::to_value(session::create(
                    &mut self.store,
                    name,
                    session_id.as_deref(),
                    &memory_ids,
                    &scratch,
                )?)?)
            }
            Operation::ApplyPolicy {
                session_id,
                scratch_paths,
            } => {
                if self.mounts.contains_key(session_id) {
                    bail!("cannot change policy while workspace is mounted");
                }
                let paths = scratch_paths.iter().map(PathBuf::from).collect::<Vec<_>>();
                session::apply_scratch_paths(&mut self.store, session_id, &paths)?;
                Ok(json!({"session_id":session_id,"applied":true}))
            }
            Operation::MountWorkspace { session_id } => {
                session::ensure_active(&self.store, session_id)?;
                self.mount(session_id)
            }
            Operation::Prefetch { session_id, paths } => {
                if !self.mounts.contains_key(session_id) {
                    bail!("workspace is not mounted");
                }
                let resident = self
                    .residents
                    .get(session_id)
                    .context("mounted workspace has no resident content store")?;
                let mut bytes = 0u64;
                for path in paths {
                    let path = normalize_relative(Path::new(path))?;
                    bytes += resident
                        .file(&path)
                        .with_context(|| format!("prefetch path is not a resident file: {path}"))?
                        .bytes
                        .len() as u64;
                }
                Ok(json!({"session_id":session_id,"files":paths.len(),"bytes":bytes}))
            }
            Operation::GetChangeJournal { session_id } => Ok(serde_json::to_value(
                session::status(&mut self.store, session_id, true)?.changes,
            )?),
            Operation::GetWorkspaceStatus { session_id } => {
                self.sync_resident_journal(session_id)?;
                Ok(serde_json::to_value(session::status(
                    &mut self.store,
                    session_id,
                    !self.residents.contains_key(session_id),
                )?)?)
            }
            Operation::ListWorkspaces { active_only } => {
                Ok(serde_json::to_value(session::list(&self.store, *active_only)?)?)
            }
            Operation::ReadFileSummary {
                session_id,
                path,
                max_bytes,
            } => {
                if !self.mounts.contains_key(session_id) {
                    bail!("workspace is not mounted");
                }
                let normalized = normalize_relative(Path::new(path))?;
                let bytes = self
                    .residents
                    .get(session_id)
                    .context("mounted workspace has no resident content store")?
                    .file(&normalized)
                    .with_context(|| format!("summary path is not a resident file: {normalized}"))?
                    .bytes;
                let limit = max_bytes.unwrap_or(4096).min(65_536);
                Ok(
                    json!({"path":normalized,"size":bytes.len(),"preview":String::from_utf8_lossy(&bytes[..bytes.len().min(limit)])}),
                )
            }
            Operation::CommitCheckpoint {
                session_id,
                paths,
                all,
            } => {
                session::ensure_active(&self.store, session_id)?;
                if self.mounts.contains_key(session_id) {
                    bail!("unmount workspace before checkpointing");
                }
                let paths = paths.iter().map(PathBuf::from).collect::<Vec<_>>();
                self.sync_resident_journal(session_id)?;
                let result = if let Some(resident) = self.residents.get(session_id) {
                    let result = session::checkpoint_resident(
                        &mut self.store,
                        session_id,
                        &paths,
                        *all,
                        resident,
                    )?;
                    resident.mark_checkpointed(&result.retained_paths)?;
                    result
                } else {
                    session::checkpoint(&mut self.store, session_id, &paths, *all)?
                };
                Ok(serde_json::to_value(result)?)
            }
            Operation::UnmountWorkspace { session_id } => self.unmount(session_id),
            Operation::CloseWorkspace { session_id } => {
                if self.mounts.contains_key(session_id) {
                    bail!("unmount workspace before closing it");
                }
                session::close(&self.store, session_id)?;
                self.residents.remove(session_id);
                Ok(json!({"session_id":session_id,"state":"closed"}))
            }
            Operation::DestroyEphemeralWorkspace { session_id } => {
                self.destroy(session_id)
            }
            Operation::Shutdown => {
                let ids = self.mounts.keys().cloned().collect::<Vec<_>>();
                for id in ids {
                    self.unmount(&id)?;
                }
                Ok(json!({"shutdown":true}))
            }
        }
    }
}
