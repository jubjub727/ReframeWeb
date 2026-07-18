fn scan_source(root: &Path, scratch: &ScratchMatcher) -> Result<Vec<FileRecord>> {
    let mut records = Vec::new();
    let entries = WalkDir::new(root)
        .follow_links(false)
        .sort_by_file_name()
        .into_iter()
        .filter_entry(|entry| {
            if entry.path() == root {
                return true;
            }
            let Ok(relative) = entry.path().strip_prefix(root) else {
                return false;
            };
            let normalized = relative.to_string_lossy().replace('\\', "/");
            !scratch.matches(&normalized)
        });
    for entry in entries {
        let entry = entry?;
        if entry.file_type().is_symlink() {
            bail!(
                "symlink sources are not supported yet: {}",
                entry.path().display()
            );
        }
        if entry.file_type().is_dir() && entry.path() != root {
            let relative = entry.path().strip_prefix(root)?;
            records.push(FileRecord {
                path: normalize_relative(relative)?,
                hash: String::new(),
                size: 0,
                source_kind: "directory".into(),
                source_ref: None,
            });
            continue;
        }
        if !entry.file_type().is_file() {
            continue;
        }
        let relative = entry.path().strip_prefix(root)?;
        let path = normalize_relative(relative)?;
        let bytes = fs::read(entry.path())?;
        records.push(FileRecord {
            path,
            hash: blake3::hash(&bytes).to_hex().to_string(),
            size: bytes.len() as u64,
            source_kind: "overlay".into(),
            source_ref: None,
        });
    }
    Ok(records)
}
fn scan_worktree(
    root: &Path,
    baseline: &BTreeMap<String, FileRecord>,
    scratch: &ScratchMatcher,
) -> Result<Vec<FileRecord>> {
    let mut records = Vec::new();
    for entry in WalkDir::new(root).follow_links(false).sort_by_file_name() {
        let entry = entry?;
        if !entry.file_type().is_file() {
            continue;
        }
        let path = normalize_relative(entry.path().strip_prefix(root)?)?;
        if scratch.matches(&path)
            || projected_file_is_unchanged(entry.path(), baseline.contains_key(&path))
        {
            continue;
        }
        let bytes = fs::read(entry.path())?;
        records.push(FileRecord {
            path,
            hash: blake3::hash(&bytes).to_hex().to_string(),
            size: bytes.len() as u64,
            source_kind: "overlay".into(),
            source_ref: None,
        });
    }
    Ok(records)
}

#[cfg(windows)]
fn projected_file_is_unchanged(path: &Path, in_baseline: bool) -> bool {
    use std::os::windows::ffi::OsStrExt;
    use windows::Win32::Storage::ProjectedFileSystem::{
        PRJ_FILE_STATE_DIRTY_PLACEHOLDER, PRJ_FILE_STATE_FULL, PrjGetOnDiskFileState,
    };
    use windows::core::PCWSTR;
    if !in_baseline {
        return false;
    }
    let wide: Vec<u16> = path.as_os_str().encode_wide().chain([0]).collect();
    match unsafe { PrjGetOnDiskFileState(PCWSTR::from_raw(wide.as_ptr())) } {
        Ok(state) => {
            !state.contains(PRJ_FILE_STATE_FULL)
                && !state.contains(PRJ_FILE_STATE_DIRTY_PLACEHOLDER)
        }
        Err(_) => false,
    }
}

#[cfg(not(windows))]
fn projected_file_is_unchanged(_path: &Path, _in_baseline: bool) -> bool {
    false
}

#[cfg(windows)]
fn baseline_path_deleted(root: &Path, path: &str) -> bool {
    use std::os::windows::ffi::OsStrExt;
    use windows::Win32::Storage::ProjectedFileSystem::{
        PRJ_FILE_STATE_TOMBSTONE, PrjGetOnDiskFileState,
    };
    use windows::core::PCWSTR;
    let native = native_path(root, path);
    let wide: Vec<u16> = native.as_os_str().encode_wide().chain([0]).collect();
    unsafe { PrjGetOnDiskFileState(PCWSTR::from_raw(wide.as_ptr())) }
        .map(|state| state.contains(PRJ_FILE_STATE_TOMBSTONE))
        .unwrap_or(false)
}

#[cfg(not(windows))]
fn baseline_path_deleted(root: &Path, path: &str) -> bool {
    !native_path(root, path).exists()
}
