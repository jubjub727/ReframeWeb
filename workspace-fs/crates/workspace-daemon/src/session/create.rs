pub fn create(
    store: &mut Store,
    name: &str,
    requested_id: Option<&str>,
    memory_ids: &[String],
    scratch_paths: &[PathBuf],
) -> Result<SessionCreated> {
    let id = requested_id
        .map(str::to_owned)
        .unwrap_or_else(|| Store::next_id("task"));
    validate_id(&id)?;
    if name.trim().is_empty() {
        bail!("session name cannot be empty");
    }
    let worktree = store.root().join("sessions").join(&id).join("worktree");
    if worktree.exists() {
        bail!("session worktree already exists: {}", worktree.display());
    }
    fs::create_dir_all(&worktree)?;
    let scratch_paths = scratch_rules(scratch_paths)?;
    let scratch_matcher = ScratchMatcher::compile(scratch_paths.iter().map(String::as_str))?;

    let mut baseline = BTreeMap::new();
    for memory_id in memory_ids {
        match store.memory_source(memory_id)? {
            PersistedMemorySource::Directory(root) => {
                for mut record in scan_source(&root, &scratch_matcher)? {
                    if record.source_kind != "directory" {
                        record.source_kind = "memory".into();
                        record.source_ref =
                            Some(serde_json::to_string(&(memory_id, &record.path))?);
                    }
                    baseline.insert(record.path.clone(), record);
                }
            }
            PersistedMemorySource::Checkpoint {
                backing_store,
                manifest_id,
            } => {
                let external = Store::open(&backing_store)?;
                for mut record in manifest_entries(&external, &manifest_id)?
                    .into_iter()
                    .filter(|record| !scratch_matcher.matches(&record.path))
                {
                    if record.source_kind == "blob" {
                        record.source_kind = "backing_blob".into();
                        record.source_ref = Some(serde_json::to_string(&(
                            &backing_store,
                            &record.hash,
                        ))?);
                    } else if record.source_kind != "tombstone"
                        && record.source_kind != "directory"
                    {
                        bail!(
                            "unsupported checkpoint entry source kind: {}",
                            record.source_kind
                        );
                    }
                    baseline.insert(record.path.clone(), record);
                }
            }
        }
    }
    let now = now_millis();
    let transaction = store.connection_mut().transaction()?;
    transaction.execute(
        "INSERT INTO workspaces(id,name,state,worktree_path,head_manifest,created_at,updated_at)\
         VALUES (?1,?2,'active',?3,?4,?5,?5)",
        params![
            id,
            name.trim(),
            worktree.to_string_lossy(),
            Option::<String>::None,
            now
        ],
    )?;
    for (ordinal, memory_id) in memory_ids.iter().enumerate() {
        transaction.execute(
            "INSERT INTO workspace_sources(workspace_id,memory_id,ordinal) VALUES (?1,?2,?3)",
            params![id, memory_id, ordinal as i64],
        )?;
    }
    for path in &scratch_paths {
        transaction.execute(
            "INSERT INTO workspace_scratch(workspace_id,path) VALUES (?1,?2)",
            params![id, path],
        )?;
    }
    for record in baseline.values() {
        transaction.execute(
            "INSERT INTO baselines(workspace_id,path,hash,size,source_kind,source_ref)\
             VALUES (?1,?2,?3,?4,?5,?6)",
            params![
                id,
                record.path,
                record.hash,
                record.size as i64,
                record.source_kind,
                record.source_ref
            ],
        )?;
    }
    transaction.commit()?;

    Ok(SessionCreated {
        session_id: id,
        worktree: worktree.to_string_lossy().into_owned(),
        memory_ids: memory_ids.to_vec(),
        projected_files: baseline
            .values()
            .filter(|record| record.source_kind != "tombstone")
            .filter(|record| record.source_kind != "directory")
            .count(),
    })
}
