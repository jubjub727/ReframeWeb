pub fn status(store: &mut Store, session_id: &str, refresh: bool) -> Result<SessionStatus> {
    if refresh {
        scan_changes(store, session_id)?;
    }
    let (name, state, worktree, head_manifest): (String, String, String, Option<String>) = store
        .connection()
        .query_row(
            "SELECT name,state,worktree_path,head_manifest FROM workspaces WHERE id=?1",
            [session_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .with_context(|| format!("unknown session: {session_id}"))?;
    Ok(SessionStatus {
        session_id: session_id.into(),
        name,
        state,
        worktree,
        head_manifest,
        memory_ids: memory_ids(store, session_id)?,
        changes: journal(store, session_id)?,
    })
}

pub fn scan_changes(store: &mut Store, session_id: &str) -> Result<Vec<Change>> {
    let worktree = worktree(store, session_id)?;
    let baseline = baseline(store, session_id)?;
    let scratch = scratch_matcher(store, session_id)?;
    let known_deleted: BTreeSet<String> = journal(store, session_id)?
        .into_iter()
        .filter(|change| change.kind == ChangeKind::Delete)
        .map(|change| change.path)
        .collect();
    let current = scan_worktree(&worktree, &baseline, &scratch)?;
    let current: BTreeMap<_, _> = current
        .into_iter()
        .filter(|record| !scratch.matches(&record.path))
        .map(|record| (record.path.clone(), record))
        .collect();
    let mut changes = Vec::new();
    for (path, record) in &current {
        match baseline.get(path) {
            None => changes.push(Change {
                path: path.clone(),
                kind: ChangeKind::Create,
                size: Some(record.size),
            }),
            Some(old) if old.hash != record.hash => changes.push(Change {
                path: path.clone(),
                kind: ChangeKind::Write,
                size: Some(record.size),
            }),
            _ => {}
        }
    }
    for (path, old) in &baseline {
        if old.source_kind != "tombstone"
            && !current.contains_key(path)
            && (known_deleted.contains(path) || baseline_path_deleted(&worktree, path))
        {
            changes.push(Change {
                path: path.clone(),
                kind: ChangeKind::Delete,
                size: None,
            });
        }
    }
    replace_journal(store, session_id, &changes)?;
    Ok(changes)
}

pub fn close(store: &Store, session_id: &str) -> Result<()> {
    let changed = store.connection().execute(
        "UPDATE workspaces SET state='closed',updated_at=?2 WHERE id=?1",
        params![session_id, now_millis()],
    )?;
    if changed == 0 {
        bail!("unknown session: {session_id}");
    }
    Ok(())
}

pub fn apply_scratch_paths(store: &mut Store, session_id: &str, paths: &[PathBuf]) -> Result<()> {
    let normalized = scratch_rules(paths)?;
    let transaction = store.connection_mut().transaction()?;
    let state: String = transaction
        .query_row(
            "SELECT state FROM workspaces WHERE id=?1",
            [session_id],
            |row| row.get(0),
        )
        .with_context(|| format!("unknown session: {session_id}"))?;
    if state != "active" {
        bail!("cannot change policy for a closed session");
    }
    transaction.execute(
        "DELETE FROM workspace_scratch WHERE workspace_id=?1",
        [session_id],
    )?;
    for path in normalized {
        transaction.execute(
            "INSERT INTO workspace_scratch(workspace_id,path) VALUES (?1,?2)",
            params![session_id, path],
        )?;
    }
    transaction.commit()?;
    Ok(())
}

pub fn destroy_ephemeral(store: &Store, session_id: &str) -> Result<()> {
    let worktree = worktree(store, session_id)?;
    let sessions_root = store.root().join("sessions").canonicalize()?;
    let session_root = worktree
        .parent()
        .context("session worktree has no parent")?;
    let canonical_parent = session_root
        .parent()
        .context("session root has no parent")?
        .canonicalize()?;
    if canonical_parent != sessions_root {
        bail!("refusing to remove a path outside the session store");
    }
    if session_root.exists() {
        fs::remove_dir_all(session_root)?;
    }
    close(store, session_id)
}
