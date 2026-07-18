use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use rusqlite::OptionalExtension;

use super::{PersistedMemorySource, PreparedMemorySource, Store, validate_memory_id};

#[path = "memories/identity.rs"]
mod identity;

pub(super) use identity::insert_or_compare_memory;

impl Store {
    #[cfg(test)]
    pub fn persist_memory_source(&self, id: &str, source: &Path) -> Result<()> {
        let prepared = self.prepare_directory_source(id, source)?;
        insert_or_compare_memory(&self.connection, &prepared)
    }

    pub(crate) fn prepare_directory_source(
        &self,
        id: &str,
        source: &Path,
    ) -> Result<PreparedMemorySource> {
        validate_memory_id(id)?;
        let source = source
            .canonicalize()
            .with_context(|| format!("memory source does not exist: {}", source.display()))?;
        if !source.is_dir() {
            bail!("memory source must be a directory: {}", source.display());
        }
        let prepared = PreparedMemorySource {
            id: id.to_owned(),
            source: PersistedMemorySource::Directory(source),
        };
        self.ensure_memory_identity_available(&prepared)?;
        Ok(prepared)
    }

    #[cfg(test)]
    pub fn persist_checkpoint_source(
        &self,
        id: &str,
        backing_store: &Path,
        manifest_id: &str,
    ) -> Result<()> {
        let prepared = self.prepare_checkpoint_source(id, backing_store, manifest_id)?;
        insert_or_compare_memory(&self.connection, &prepared)
    }

    pub(crate) fn prepare_checkpoint_source(
        &self,
        id: &str,
        backing_store: &Path,
        manifest_id: &str,
    ) -> Result<PreparedMemorySource> {
        validate_memory_id(id)?;
        let backing_store = backing_store.canonicalize().with_context(|| {
            format!(
                "checkpoint backing store does not exist: {}",
                backing_store.display()
            )
        })?;
        let external = Self::open(&backing_store)?;
        if !external.manifest_exists(manifest_id)? {
            bail!("checkpoint manifest does not exist: {manifest_id}");
        }
        let prepared = PreparedMemorySource {
            id: id.to_owned(),
            source: PersistedMemorySource::Checkpoint {
                backing_store,
                manifest_id: manifest_id.to_owned(),
            },
        };
        self.ensure_memory_identity_available(&prepared)?;
        Ok(prepared)
    }

    #[cfg(test)]
    pub(crate) fn prepare_registered_source(&self, id: &str) -> Result<PreparedMemorySource> {
        validate_memory_id(id)?;
        Ok(PreparedMemorySource {
            id: id.to_owned(),
            source: self.memory_source(id)?,
        })
    }

    fn ensure_memory_identity_available(&self, prepared: &PreparedMemorySource) -> Result<()> {
        identity::ensure_available(&self.connection, prepared)
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
            Some((path, kind, _)) if kind == "directory" => directory_source(path),
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
}

fn directory_source(path: String) -> Result<PersistedMemorySource> {
    let path = PathBuf::from(path);
    if !path.is_dir() {
        bail!("memory source is unavailable: {}", path.display());
    }
    Ok(PersistedMemorySource::Directory(path))
}
