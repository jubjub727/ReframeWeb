use std::fs::{self, OpenOptions};
use std::io::{Seek, SeekFrom, Write};
use std::path::PathBuf;

use anyhow::{Context, Result, bail};

pub struct ScratchBackend {
    root: PathBuf,
}

impl ScratchBackend {
    pub fn new(root: PathBuf) -> Result<Self> {
        fs::create_dir_all(&root)?;
        Ok(Self { root })
    }

    pub fn metadata(&self, path: &str) -> Option<std::fs::Metadata> {
        fs::metadata(self.path(path)).ok()
    }

    pub fn entries(&self, path: &str) -> Result<Vec<(String, bool, u64)>> {
        let mut entries = Vec::new();
        let directory = self.path(path);
        if !directory.is_dir() {
            return Ok(entries);
        }
        for entry in fs::read_dir(directory)? {
            let entry = entry?;
            let metadata = entry.metadata()?;
            let name = entry
                .file_name()
                .into_string()
                .map_err(|_| anyhow::anyhow!("scratch paths must be UTF-8"))?;
            entries.push((name, metadata.is_dir(), metadata.len()));
        }
        entries.sort_by(|left, right| left.0.cmp(&right.0));
        Ok(entries)
    }

    pub fn create_directory(&self, path: &str) -> Result<()> {
        let native = self.path(path);
        if let Some(parent) = native.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::create_dir(native).map_err(Into::into)
    }

    pub fn create_file(&self, path: &str) -> Result<()> {
        let native = self.path(path);
        if let Some(parent) = native.parent() {
            fs::create_dir_all(parent)?;
        }
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(native)?;
        Ok(())
    }

    pub fn read(&self, path: &str, offset: u64, size: u32) -> Result<Vec<u8>> {
        let bytes = fs::read(self.path(path))?;
        let start = usize::try_from(offset).context("scratch read offset exceeds address space")?;
        if start >= bytes.len() {
            return Ok(Vec::new());
        }
        let end = start.saturating_add(size as usize).min(bytes.len());
        Ok(bytes[start..end].to_vec())
    }

    pub fn write(&self, path: &str, offset: u64, data: &[u8]) -> Result<()> {
        let mut file = OpenOptions::new().write(true).open(self.path(path))?;
        file.seek(SeekFrom::Start(offset))?;
        file.write_all(data)?;
        Ok(())
    }

    pub fn resize(&self, path: &str, size: u64) -> Result<()> {
        OpenOptions::new()
            .write(true)
            .open(self.path(path))?
            .set_len(size)?;
        Ok(())
    }

    pub fn remove(&self, path: &str, directory: bool) -> Result<()> {
        if directory {
            fs::remove_dir(self.path(path))?;
        } else {
            fs::remove_file(self.path(path))?;
        }
        Ok(())
    }

    pub fn rename(&self, source: &str, destination: &str) -> Result<()> {
        let destination = self.path(destination);
        if let Some(parent) = destination.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::rename(self.path(source), destination)?;
        Ok(())
    }

    fn path(&self, normalized: &str) -> PathBuf {
        normalized
            .split('/')
            .filter(|part| !part.is_empty())
            .fold(self.root.clone(), |path, part| path.join(part))
    }
}

pub fn ensure_same_storage(left: bool, right: bool) -> Result<()> {
    if left != right {
        bail!("cannot move between resident and direct-disk storage")
    }
    Ok(())
}
