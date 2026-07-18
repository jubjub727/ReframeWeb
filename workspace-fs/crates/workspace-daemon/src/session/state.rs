pub fn worktree(store: &Store, session_id: &str) -> Result<PathBuf> {
    let value: Option<String> = store
        .connection()
        .query_row(
            "SELECT worktree_path FROM workspaces WHERE id=?1",
            [session_id],
            |row| row.get(0),
        )
        .optional()?;
    value
        .map(PathBuf::from)
        .ok_or_else(|| anyhow::anyhow!("unknown session: {session_id}"))
}

pub fn scratch_paths(store: &Store, session_id: &str) -> Result<Vec<String>> {
    let mut statement = store
        .connection()
        .prepare("SELECT path FROM workspace_scratch WHERE workspace_id=?1 ORDER BY path")?;
    let rows = statement.query_map([session_id], |row| row.get(0))?;
    rows.collect::<rusqlite::Result<Vec<_>>>()
        .map_err(Into::into)
}

pub fn ensure_active(store: &Store, session_id: &str) -> Result<()> {
    let state: String = store
        .connection()
        .query_row(
            "SELECT state FROM workspaces WHERE id=?1",
            [session_id],
            |row| row.get(0),
        )
        .with_context(|| format!("unknown session: {session_id}"))?;
    if state != "active" {
        bail!("workspace is closed: {session_id}");
    }
    Ok(())
}

pub fn scratch_matcher(store: &Store, session_id: &str) -> Result<ScratchMatcher> {
    let paths = scratch_paths(store, session_id)?;
    ScratchMatcher::compile(paths.iter().map(String::as_str))
}

pub fn list(store: &Store, active_only: bool) -> Result<Vec<SessionSummary>> {
    let condition = if active_only { "WHERE state='active'" } else { "" };
    let query = format!(
        "SELECT id,name,state,head_manifest,created_at,updated_at FROM workspaces \
         {condition} ORDER BY created_at DESC"
    );
    let rows = {
        let mut statement = store.connection().prepare(&query)?;
        let rows = statement.query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, Option<String>>(3)?,
                row.get::<_, i64>(4)?,
                row.get::<_, i64>(5)?,
            ))
        })?;
        rows.collect::<rusqlite::Result<Vec<_>>>()?
    };
    rows.into_iter()
        .map(|(id, name, state, head_manifest, created_at, updated_at)| {
            Ok(SessionSummary {
                memory_ids: memory_ids(store, &id)?,
                session_id: id,
                name,
                state,
                head_manifest,
                created_at,
                updated_at,
            })
        })
        .collect()
}

pub fn baseline(store: &Store, session_id: &str) -> Result<BTreeMap<String, FileRecord>> {
    let mut statement = store.connection().prepare(
        "SELECT path,hash,size,source_kind,source_ref FROM baselines WHERE workspace_id=?1 ORDER BY path",
    )?;
    let rows = statement.query_map([session_id], |row| {
        Ok(FileRecord {
            path: row.get(0)?,
            hash: row.get(1)?,
            size: row.get::<_, i64>(2)? as u64,
            source_kind: row.get(3)?,
            source_ref: row.get(4)?,
        })
    })?;
    Ok(rows
        .collect::<rusqlite::Result<Vec<_>>>()?
        .into_iter()
        .map(|r| (r.path.clone(), r))
        .collect())
}

include!("scanning.rs");
fn manifest_entries(store: &Store, manifest: &str) -> Result<Vec<FileRecord>> {
    let mut statement = store.connection().prepare(
        "SELECT path,hash,size,source_kind,source_ref FROM manifest_entries WHERE manifest_id=?1 ORDER BY path",
    )?;
    let rows = statement.query_map([manifest], |row| {
        Ok(FileRecord {
            path: row.get(0)?,
            hash: row.get(1)?,
            size: row.get::<_, i64>(2)? as u64,
            source_kind: row.get(3)?,
            source_ref: row.get(4)?,
        })
    })?;
    rows.collect::<rusqlite::Result<Vec<_>>>()
        .map_err(Into::into)
}

fn memory_ids(store: &Store, session_id: &str) -> Result<Vec<String>> {
    let mut statement = store.connection().prepare(
        "SELECT memory_id FROM workspace_sources WHERE workspace_id=?1 ORDER BY ordinal",
    )?;
    let rows = statement.query_map([session_id], |row| row.get(0))?;
    rows.collect::<rusqlite::Result<Vec<_>>>()
        .map_err(Into::into)
}

fn journal(store: &Store, session_id: &str) -> Result<Vec<Change>> {
    let mut statement = store
        .connection()
        .prepare("SELECT path,kind,size FROM journal_events WHERE workspace_id=?1 ORDER BY path")?;
    let rows = statement.query_map([session_id], |row| {
        let kind: String = row.get(1)?;
        let kind = match kind.as_str() {
            "create" => ChangeKind::Create,
            "write" => ChangeKind::Write,
            _ => ChangeKind::Delete,
        };
        Ok(Change {
            path: row.get(0)?,
            kind,
            size: row.get::<_, Option<i64>>(2)?.map(|v| v as u64),
        })
    })?;
    rows.collect::<rusqlite::Result<Vec<_>>>()
        .map_err(Into::into)
}

pub fn replace_journal(store: &mut Store, session_id: &str, changes: &[Change]) -> Result<()> {
    let transaction = store.connection_mut().transaction()?;
    transaction.execute(
        "DELETE FROM journal_events WHERE workspace_id=?1",
        [session_id],
    )?;
    for change in changes {
        transaction.execute(
            "INSERT INTO journal_events(workspace_id,path,kind,size,scanned_at) VALUES (?1,?2,?3,?4,?5)",
            params![session_id, change.path, change.kind.as_str(), change.size.map(|v| v as i64), now_millis()],
        )?;
    }
    transaction.commit()?;
    Ok(())
}
