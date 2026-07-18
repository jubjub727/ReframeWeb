use std::fs::{self, File, OpenOptions};
use std::path::PathBuf;

use anyhow::{Result, bail};
use fuser::OpenFlags;

use super::handles::OpenAccess;

pub struct ScratchBackend {
    root: PathBuf,
}

impl ScratchBackend {
    pub fn new(root: PathBuf) -> Result<Self> {
        fs::create_dir_all(&root)?;
        Ok(Self { root })
    }

    pub fn metadata(&self, path: &str) -> Result<Option<std::fs::Metadata>> {
        match fs::metadata(self.path(path)) {
            Ok(metadata) => Ok(Some(metadata)),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
            Err(error) => Err(error.into()),
        }
    }

    pub fn entries(&self, path: &str) -> Result<Vec<(String, bool, u64)>> {
        let mut entries = Vec::new();
        let directory = self.path(path);
        let directory = match fs::read_dir(directory) {
            Ok(directory) => directory,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(entries),
            Err(error) => return Err(error.into()),
        };
        for entry in directory {
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

    pub fn create_file(&self, path: &str, flags: OpenFlags) -> Result<File> {
        let native = self.path(path);
        if let Some(parent) = native.parent() {
            fs::create_dir_all(parent)?;
        }
        let access = OpenAccess::from_flags(flags);
        OpenOptions::new()
            .read(access.readable())
            .write(true)
            .create_new(true)
            .open(native)
            .map_err(Into::into)
    }

    pub fn open(&self, path: &str, flags: OpenFlags) -> Result<File> {
        let access = OpenAccess::from_flags(flags);
        OpenOptions::new()
            .read(access.readable())
            .write(access.writable())
            .truncate(access.writable() && flags.0 & libc::O_TRUNC != 0)
            .open(self.path(path))
            .map_err(Into::into)
    }

    pub fn resize_path(&self, path: &str, size: u64) -> Result<()> {
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
