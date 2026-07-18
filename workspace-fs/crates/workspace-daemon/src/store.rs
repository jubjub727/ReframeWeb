use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, bail};
use rusqlite::{Connection, OptionalExtension, params};

pub struct Store {
    root: PathBuf,
    connection: Connection,
}

pub enum PersistedMemorySource {
    Directory(PathBuf),
    Checkpoint {
        backing_store: PathBuf,
        manifest_id: String,
    },
}

impl Store {
    pub fn open(root: &Path) -> Result<Self> {
        fs::create_dir_all(root).with_context(|| format!("create store {}", root.display()))?;
        fs::create_dir_all(root.join("blobs"))?;
        fs::create_dir_all(root.join("sessions"))?;
        let connection = Connection::open(root.join("workspace.sqlite3"))?;
        connection.pragma_update(None, "journal_mode", "WAL")?;
        connection.pragma_update(None, "foreign_keys", "ON")?;
        let mut store = Self {
            root: root.to_path_buf(),
            connection,
        };
        store.migrate()?;
        Ok(store)
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    pub fn connection(&self) -> &Connection {
        &self.connection
    }

    pub fn connection_mut(&mut self) -> &mut Connection {
        &mut self.connection
    }

    pub fn persist_memory_source(&self, id: &str, source: &Path) -> Result<()> {
        if id.is_empty() || id.len() > 256 {
            bail!("resolved memory id must be between 1 and 256 characters");
        }
        let source = source
            .canonicalize()
            .with_context(|| format!("memory source does not exist: {}", source.display()))?;
        if !source.is_dir() {
            bail!("memory source must be a directory: {}", source.display());
        }
        self.connection.execute(
            "INSERT INTO memories(id,source_path,source_kind,manifest_id,created_at)\
             VALUES (?1,?2,'directory',NULL,?3)\
             ON CONFLICT(id) DO UPDATE SET source_path=excluded.source_path,\
             source_kind='directory',manifest_id=NULL",
            params![id, source.to_string_lossy(), now_millis()],
        )?;
        Ok(())
    }

    pub fn persist_checkpoint_source(
        &self,
        id: &str,
        backing_store: &Path,
        manifest_id: &str,
    ) -> Result<()> {
        validate_memory_id(id)?;
        let backing_store = backing_store.canonicalize().with_context(|| {
            format!(
                "checkpoint backing store does not exist: {}",
                backing_store.display()
            )
        })?;
        let external = Self::open(&backing_store)?;
        let exists: bool = external.connection.query_row(
            "SELECT EXISTS(SELECT 1 FROM manifests WHERE id=?1)",
            [manifest_id],
            |row| row.get(0),
        )?;
        if !exists {
            bail!("checkpoint manifest does not exist: {manifest_id}");
        }
        self.connection.execute(
            "INSERT INTO memories(id,source_path,source_kind,manifest_id,created_at)\
             VALUES (?1,?2,'checkpoint',?3,?4)\
             ON CONFLICT(id) DO UPDATE SET source_path=excluded.source_path,\
             source_kind='checkpoint',manifest_id=excluded.manifest_id",
            params![
                id,
                backing_store.to_string_lossy(),
                manifest_id,
                now_millis()
            ],
        )?;
        Ok(())
    }

    pub fn memory_source(&self, id: &str) -> Result<PersistedMemorySource> {
        let value: Option<(String, String, Option<String>)> = self
            .connection
            .query_row(
                "SELECT source_path,source_kind,manifest_id FROM memories WHERE id=?1",
                [id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .optional()?;
        match value {
            Some((path, kind, _)) if kind == "directory" => {
                let path = PathBuf::from(path);
                if !path.is_dir() {
                    bail!("memory source is unavailable: {}", path.display());
                }
                Ok(PersistedMemorySource::Directory(path))
            }
            Some((path, kind, Some(manifest_id))) if kind == "checkpoint" => {
                Ok(PersistedMemorySource::Checkpoint {
                    backing_store: PathBuf::from(path),
                    manifest_id,
                })
            }
            Some((_, kind, _)) => bail!("invalid persisted memory source kind: {kind}"),
            None => bail!("unknown memory: {id}"),
        }
    }

    pub fn memory_path(&self, id: &str) -> Result<PathBuf> {
        match self.memory_source(id)? {
            PersistedMemorySource::Directory(path) => Ok(path),
            PersistedMemorySource::Checkpoint { .. } => {
                bail!("checkpoint memory does not have a directory source: {id}")
            }
        }
    }

    pub fn put_blob(&self, bytes: &[u8]) -> Result<String> {
        let hash = blake3::hash(bytes).to_hex().to_string();
        let destination = self.blob_path(&hash);
        if !destination.exists() {
            if let Some(parent) = destination.parent() {
                fs::create_dir_all(parent)?;
            }
            let temporary = destination.with_extension(format!("tmp-{}", std::process::id()));
            fs::write(&temporary, bytes)?;
            match fs::rename(&temporary, &destination) {
                Ok(()) => {}
                Err(error) if destination.exists() => {
                    let _ = fs::remove_file(temporary);
                    drop(error);
                }
                Err(error) => return Err(error.into()),
            }
        }
        Ok(hash)
    }

    pub fn read_blob(&self, hash: &str) -> Result<Vec<u8>> {
        fs::read(self.blob_path(hash)).with_context(|| format!("missing retained blob {hash}"))
    }

    pub fn next_id(prefix: &str) -> String {
        format!("{prefix}-{:x}-{:x}", now_millis(), std::process::id())
    }

    fn blob_path(&self, hash: &str) -> PathBuf {
        self.root.join("blobs").join(&hash[..2]).join(hash)
    }

    fn migrate(&mut self) -> Result<()> {
        self.connection.execute_batch(include_str!("schema.sql"))?;
        self.ensure_memory_column("source_kind", "TEXT NOT NULL DEFAULT 'directory'")?;
        self.ensure_memory_column("manifest_id", "TEXT")?;
        Ok(())
    }

    fn ensure_memory_column(&self, name: &str, definition: &str) -> Result<()> {
        let mut statement = self.connection.prepare("PRAGMA table_info(memories)")?;
        let columns = statement
            .query_map([], |row| row.get::<_, String>(1))?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        if !columns.iter().any(|column| column == name) {
            self.connection.execute_batch(&format!(
                "ALTER TABLE memories ADD COLUMN {name} {definition}"
            ))?;
        }
        Ok(())
    }
}

fn validate_memory_id(id: &str) -> Result<()> {
    if id.is_empty() || id.len() > 256 {
        bail!("resolved memory id must be between 1 and 256 characters");
    }
    Ok(())
}

pub fn validate_id(id: &str) -> Result<()> {
    if id.is_empty()
        || id.len() > 96
        || !id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"-_".contains(&b))
    {
        bail!("ids may contain only ASCII letters, numbers, '-' and '_' (max 96)");
    }
    Ok(())
}

pub fn now_millis() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as i64
}
