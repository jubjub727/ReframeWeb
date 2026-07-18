pub fn checkpoint(
    store: &mut Store,
    session_id: &str,
    includes: &[PathBuf],
    all: bool,
) -> Result<CheckpointResult> {
    checkpoint_with_reader(
        store,
        session_id,
        includes,
        all,
        |worktree, path| fs::read(native_path(worktree, path)).map_err(Into::into),
        |worktree, path| native_path(worktree, path).is_dir(),
    )
}
pub fn checkpoint_resident(
    store: &mut Store,
    session_id: &str,
    includes: &[PathBuf],
    all: bool,
    resident: &crate::resident::ResidentWorkspace,
) -> Result<CheckpointResult> {
    checkpoint_with_reader(
        store,
        session_id,
        includes,
        all,
        |_worktree, path| {
            resident
                .file(path)
                .map(|file| file.bytes.to_vec())
                .ok_or_else(|| anyhow::anyhow!("resident checkpoint file is missing: {path}"))
        },
        |_worktree, path| resident.is_directory(path),
    )
}

fn checkpoint_with_reader(
    store: &mut Store,
    session_id: &str,
    includes: &[PathBuf],
    all: bool,
    read: impl Fn(&Path, &str) -> Result<Vec<u8>>,
    is_directory: impl Fn(&Path, &str) -> bool,
) -> Result<CheckpointResult> {
    let changes = journal(store, session_id)?;
    let scratch = scratch_matcher(store, session_id)?;
    if !all && includes.is_empty() {
        bail!("checkpoint defaults to discard; pass --include PATH or --all");
    }
    let selected: BTreeSet<String> = if all {
        changes.iter().map(|change| change.path.clone()).collect()
    } else {
        includes
            .iter()
            .map(|path| normalize_relative(path))
            .collect::<Result<_>>()?
    };
    let changed: BTreeSet<_> = changes.iter().map(|change| change.path.as_str()).collect();
    for path in &selected {
        if !changed.contains(path.as_str()) {
            bail!("checkpoint path is not changed: {path}");
        }
        if scratch.matches(path) {
            bail!("scratch paths can never be checkpointed: {path}");
        }
    }

    let worktree = worktree(store, session_id)?;
    let parent: Option<String> = store.connection().query_row(
        "SELECT head_manifest FROM workspaces WHERE id=?1",
        [session_id],
        |row| row.get(0),
    )?;
    let mut retained = if let Some(ref parent) = parent {
        manifest_entries(store, parent)?
            .into_iter()
            .map(|r| (r.path.clone(), r))
            .collect()
    } else {
        BTreeMap::new()
    };

    for change in &changes {
        if !selected.contains(&change.path) {
            continue;
        }
        match change.kind {
            ChangeKind::Delete => {
                retained.insert(
                    change.path.clone(),
                    FileRecord {
                        path: change.path.clone(),
                        hash: String::new(),
                        size: 0,
                        source_kind: "tombstone".into(),
                        source_ref: None,
                    },
                );
            }
            ChangeKind::Create | ChangeKind::Write => {
                if is_directory(&worktree, &change.path) {
                    retained.insert(
                        change.path.clone(),
                        FileRecord {
                            path: change.path.clone(),
                            hash: String::new(),
                            size: 0,
                            source_kind: "directory".into(),
                            source_ref: None,
                        },
                    );
                    continue;
                }
                let bytes = read(&worktree, &change.path)?;
                let hash = store.put_blob(&bytes)?;
                retained.insert(
                    change.path.clone(),
                    FileRecord {
                        path: change.path.clone(),
                        hash,
                        size: bytes.len() as u64,
                        source_kind: "blob".into(),
                        source_ref: None,
                    },
                );
            }
        }
    }

    let manifest_id = Store::next_id("manifest");
    let now = now_millis();
    let transaction = store.connection_mut().transaction()?;
    transaction.execute(
        "INSERT INTO manifests(id,workspace_id,parent_id,created_at) VALUES (?1,?2,?3,?4)",
        params![manifest_id, session_id, parent, now],
    )?;
    for record in retained.values() {
        transaction.execute(
            "INSERT INTO manifest_entries(manifest_id,path,hash,size,source_kind,source_ref)\
             VALUES (?1,?2,?3,?4,?5,?6)",
            params![
                manifest_id,
                record.path,
                record.hash,
                record.size as i64,
                record.source_kind,
                record.source_ref
            ],
        )?;
    }
    transaction.execute(
        "UPDATE workspaces SET head_manifest=?2,updated_at=?3 WHERE id=?1",
        params![session_id, manifest_id, now],
    )?;
    for path in &selected {
        if let Some(record) = retained.get(path) {
            transaction.execute(
                "INSERT INTO baselines(workspace_id,path,hash,size,source_kind,source_ref) VALUES (?1,?2,?3,?4,?5,NULL)\
                 ON CONFLICT(workspace_id,path) DO UPDATE SET hash=excluded.hash,size=excluded.size,source_kind=excluded.source_kind,source_ref=NULL",
                params![session_id, path, record.hash, record.size as i64, record.source_kind],
            )?;
        } else {
            transaction.execute(
                "DELETE FROM baselines WHERE workspace_id=?1 AND path=?2",
                params![session_id, path],
            )?;
        }
        transaction.execute(
            "DELETE FROM journal_events WHERE workspace_id=?1 AND path=?2",
            params![session_id, path],
        )?;
    }
    transaction.commit()?;
    let remaining_changes = journal(store, session_id)?;
    Ok(CheckpointResult {
        session_id: session_id.into(),
        manifest_id,
        retained_paths: selected.into_iter().collect(),
        remaining_changes,
    })
}
