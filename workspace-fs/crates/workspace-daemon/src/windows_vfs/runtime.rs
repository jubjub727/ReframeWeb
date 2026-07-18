use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use anyhow::Result;
use windows::Win32::Storage::FileSystem::{FILE_ATTRIBUTE_TEMPORARY, SetFileAttributesW};
use windows::core::GUID;
use windows::core::PCWSTR;

use crate::paths::{ScratchMatcher, native_path};
use crate::resident::{ResidentFile, ResidentWorkspace};
use crate::session;
use crate::store::Store;

#[derive(Clone)]
pub struct DirectoryEntry {
    pub name: String,
    pub is_directory: bool,
    pub size: u64,
}

pub struct Enumeration {
    pub entries: Vec<DirectoryEntry>,
    pub next: usize,
    pub expression: String,
}

pub struct Runtime {
    store_root: PathBuf,
    session_id: String,
    worktree: PathBuf,
    worktree_wide: Vec<u16>,
    resident: Arc<ResidentWorkspace>,
    scratch: ScratchMatcher,
    pub enumerations: Mutex<HashMap<GUID, Enumeration>>,
}

impl Runtime {
    pub fn load(
        store_root: &Path,
        session_id: &str,
        resident: Arc<ResidentWorkspace>,
    ) -> Result<Self> {
        let store = Store::open(store_root)?;
        let worktree = session::worktree(&store, session_id)?;
        let mut worktree_wide: Vec<u16> = worktree.as_os_str().encode_wide().collect();
        worktree_wide.push(0);
        let scratch = session::scratch_matcher(&store, session_id)?;
        Ok(Self {
            store_root: store_root.to_path_buf(),
            session_id: session_id.into(),
            worktree,
            worktree_wide,
            resident,
            scratch,
            enumerations: Mutex::new(HashMap::new()),
        })
    }

    pub fn worktree_wide(&self) -> &[u16] {
        &self.worktree_wide
    }

    pub fn file(&self, path: &str) -> Option<ResidentFile> {
        self.resident.file(path)
    }

    pub fn exists(&self, path: &str) -> bool {
        self.resident.contains_path(path)
    }

    pub fn entries(&self, directory: &str) -> Vec<DirectoryEntry> {
        self.resident
            .entries(directory)
            .into_iter()
            .map(|(name, is_directory, size)| DirectoryEntry {
                name,
                is_directory,
                size,
            })
            .collect()
    }

    pub fn absorb_native_file(&self, path: &str) -> Result<()> {
        let bytes = std::fs::read(native_path(&self.worktree, path))?;
        let kind = self.resident.replace(path, bytes)?;
        self.record_notification(path, kind.as_str())
    }

    pub fn remove_resident(&self, path: &str) -> Result<()> {
        self.resident.remove(path)?;
        self.record_notification(path, "delete")
    }

    pub fn create_resident_directory(&self, path: &str) -> Result<()> {
        self.resident.create_directory(path)
    }

    pub fn rename_resident(&self, source: &str, destination: &str) -> Result<()> {
        self.resident.rename(source, destination)?;
        self.record_notification(source, "delete")?;
        self.record_notification(destination, "create")
    }

    pub fn mark_temporary(&self, path: &str) -> Result<()> {
        let native = native_path(&self.worktree, path);
        let wide: Vec<u16> = native.as_os_str().encode_wide().chain([0]).collect();
        unsafe { SetFileAttributesW(PCWSTR::from_raw(wide.as_ptr()), FILE_ATTRIBUTE_TEMPORARY) }?;
        Ok(())
    }

    pub fn is_scratch(&self, path: &str) -> bool {
        self.scratch.matches(path)
    }

    pub fn record_notification(&self, path: &str, kind: &str) -> Result<()> {
        if self.scratch.matches(path) {
            return Ok(());
        }
        let store = Store::open(&self.store_root)?;
        store.connection().execute(
            "INSERT INTO journal_events(workspace_id,path,kind,size,scanned_at) VALUES (?1,?2,?3,NULL,?4)\
             ON CONFLICT(workspace_id,path) DO UPDATE SET kind=excluded.kind,size=NULL,scanned_at=excluded.scanned_at",
            rusqlite::params![self.session_id, path, kind, crate::store::now_millis()],
        )?;
        Ok(())
    }
}

use std::os::windows::ffi::OsStrExt;
