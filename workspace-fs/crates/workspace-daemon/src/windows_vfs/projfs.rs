use std::os::windows::ffi::OsStrExt;

use anyhow::{Context, Result};
use walkdir::WalkDir;
use windows::Win32::Foundation::ERROR_FILE_NOT_FOUND;
use windows::Win32::Storage::ProjectedFileSystem::{
    PRJ_CALLBACKS, PRJ_FLAG_USE_NEGATIVE_PATH_CACHE, PRJ_NAMESPACE_VIRTUALIZATION_CONTEXT,
    PRJ_NOTIFICATION_MAPPING, PRJ_NOTIFY_FILE_HANDLE_CLOSED_FILE_DELETED,
    PRJ_NOTIFY_FILE_HANDLE_CLOSED_FILE_MODIFIED, PRJ_NOTIFY_FILE_RENAMED,
    PRJ_NOTIFY_NEW_FILE_CREATED, PRJ_NOTIFY_PRE_RENAME, PRJ_NOTIFY_PRE_SET_HARDLINK,
    PRJ_STARTVIRTUALIZING_OPTIONS, PRJ_UPDATE_ALLOW_DIRTY_DATA, PRJ_UPDATE_ALLOW_DIRTY_METADATA,
    PRJ_UPDATE_ALLOW_READ_ONLY, PRJ_UPDATE_ALLOW_TOMBSTONE, PrjDeleteFile,
    PrjMarkDirectoryAsPlaceholder, PrjStartVirtualizing, PrjStopVirtualizing,
};
use windows::core::{GUID, HRESULT, PCWSTR};

use super::runtime::Runtime;
use crate::resident::ResidentWorkspace;
use crate::session;
use crate::store::Store;

pub(super) struct Provider {
    context: PRJ_NAMESPACE_VIRTUALIZATION_CONTEXT,
    _runtime: Box<Runtime>,
    stopped: bool,
    pub(super) worktree: std::path::PathBuf,
}

impl Provider {
    pub(super) fn start(
        store: &Store,
        session_id: &str,
        resident: std::sync::Arc<ResidentWorkspace>,
    ) -> Result<Self> {
        let worktree = session::worktree(store, session_id)?;
        let runtime = Box::new(Runtime::load(store, session_id, resident)?);
        let scratch_paths = store.scratch_paths(session_id)?;
        let instance_id = instance_id(session_id);
        unsafe {
            PrjMarkDirectoryAsPlaceholder(
                PCWSTR::from_raw(runtime.worktree_wide().as_ptr()),
                PCWSTR::null(),
                None,
                &instance_id,
            )
        }
        .context("mark the session worktree as a ProjFS virtualization root; enable the Windows Projected File System optional feature if this failed")?;
        let callbacks = PRJ_CALLBACKS {
            StartDirectoryEnumerationCallback: Some(super::callbacks::start_enumeration),
            EndDirectoryEnumerationCallback: Some(super::callbacks::end_enumeration),
            GetDirectoryEnumerationCallback: Some(super::callbacks::get_enumeration),
            GetPlaceholderInfoCallback: Some(super::callbacks::get_placeholder),
            GetFileDataCallback: Some(super::callbacks::get_file_data),
            QueryFileNameCallback: Some(super::callbacks::query_file_name),
            NotificationCallback: Some(super::callbacks::notification),
            CancelCommandCallback: None,
        };
        let notification_root = [0u16];
        let mut mapping = PRJ_NOTIFICATION_MAPPING {
            NotificationBitMask: PRJ_NOTIFY_NEW_FILE_CREATED
                | PRJ_NOTIFY_FILE_HANDLE_CLOSED_FILE_MODIFIED
                | PRJ_NOTIFY_FILE_HANDLE_CLOSED_FILE_DELETED
                | PRJ_NOTIFY_PRE_RENAME
                | PRJ_NOTIFY_PRE_SET_HARDLINK
                | PRJ_NOTIFY_FILE_RENAMED,
            NotificationRoot: PCWSTR::from_raw(notification_root.as_ptr()),
        };
        let options = PRJ_STARTVIRTUALIZING_OPTIONS {
            Flags: PRJ_FLAG_USE_NEGATIVE_PATH_CACHE,
            PoolThreadCount: 0,
            ConcurrentThreadCount: 0,
            NotificationMappings: &mut mapping,
            NotificationMappingsCount: 1,
        };
        let context = match unsafe {
            PrjStartVirtualizing(
                PCWSTR::from_raw(runtime.worktree_wide().as_ptr()),
                &callbacks,
                Some((&*runtime as *const Runtime).cast_mut().cast()),
                Some(&options),
            )
        } {
            Ok(context) => context,
            Err(error) => return Err(error).context("start ProjFS virtualization"),
        };
        for path in scratch_paths {
            if !crate::paths::is_literal_rule(&path) {
                continue;
            }
            if let Err(error) = std::fs::create_dir_all(crate::paths::native_path(&worktree, &path))
            {
                unsafe {
                    PrjStopVirtualizing(context);
                }
                return Err(error).context("create direct-disk scratch path");
            }
        }

        Ok(Self {
            context,
            _runtime: runtime,
            stopped: false,
            worktree,
        })
    }

    pub(super) fn clear_cached_tree(&mut self) -> Result<()> {
        let entries = WalkDir::new(&self.worktree)
            .min_depth(1)
            .contents_first(true);
        for entry in entries {
            let entry = entry?;
            let relative = entry.path().strip_prefix(&self.worktree)?;
            let name: Vec<u16> = relative.as_os_str().encode_wide().chain([0]).collect();
            let flags = PRJ_UPDATE_ALLOW_DIRTY_DATA
                | PRJ_UPDATE_ALLOW_DIRTY_METADATA
                | PRJ_UPDATE_ALLOW_READ_ONLY
                | PRJ_UPDATE_ALLOW_TOMBSTONE;
            let result = unsafe {
                PrjDeleteFile(
                    self.context,
                    PCWSTR::from_raw(name.as_ptr()),
                    Some(flags),
                    None,
                )
            };
            if let Err(error) = result {
                if error.code() != HRESULT::from_win32(ERROR_FILE_NOT_FOUND.0) {
                    return Err(error).with_context(|| {
                        format!("clear cached workspace item {}", entry.path().display())
                    });
                }
            }
        }
        Ok(())
    }

    pub(super) fn unmount(&mut self) -> Result<()> {
        self.clear_cached_tree()?;
        self.stop();
        Ok(())
    }

    pub(super) fn is_mounted(&self) -> bool {
        !self.stopped
    }

    fn stop(&mut self) {
        if !self.stopped {
            unsafe {
                PrjStopVirtualizing(self.context);
            }
            self.stopped = true;
        }
    }
}

impl Drop for Provider {
    fn drop(&mut self) {
        self.stop();
    }
}

fn instance_id(session_id: &str) -> GUID {
    let bytes = blake3::hash(session_id.as_bytes());
    let value: [u8; 16] = bytes.as_bytes()[..16].try_into().expect("fixed hash size");
    GUID::from_u128(u128::from_le_bytes(value))
}
