use std::ffi::OsStr;

use fuser::{Errno, FileType, INodeNo};

use super::child_path;
use crate::unix_vfs::error::errno;
use crate::unix_vfs::filesystem::{PathMetadata, ResidentFuse};
use crate::unix_vfs::scratch::ensure_same_storage;

impl ResidentFuse {
    pub(in crate::unix_vfs) fn remove_child(
        &self,
        parent_inode: INodeNo,
        entry_name: &OsStr,
        directory: bool,
    ) -> Result<(), Errno> {
        let mut handles = self.handles.lock().map_err(|_| Errno::EIO)?;
        let mut inodes = self.inodes.lock().map_err(|_| Errno::EIO)?;
        let path = child_path(self, &inodes, parent_inode, entry_name)?;
        let metadata = self.path_metadata(&path)?;
        validate_remove(metadata.kind, directory)?;
        if directory && !self.entries_unlocked(&path)?.is_empty() {
            return Err(Errno::ENOTEMPTY);
        }
        if self.resident.is_scratch(&path) {
            self.scratch
                .remove(&path, directory)
                .map_err(|error| errno("remove scratch path", &error))?;
        } else {
            handles.unlink_resident(
                &path,
                |linked_path| {
                    self.resident
                        .file(linked_path)
                        .map(|file| file.bytes.to_vec())
                        .ok_or(Errno::ENOENT)
                },
                || {
                    self.resident
                        .remove(&path)
                        .map_err(|error| errno("remove resident path", &error))
                },
            )?;
        }
        inodes.remove_path(&path);
        Ok(())
    }

    pub(in crate::unix_vfs) fn rename_child(
        &self,
        parent_inode: INodeNo,
        old_name: &OsStr,
        new_parent_inode: INodeNo,
        new_name: &OsStr,
    ) -> Result<(), Errno> {
        let mut handles = self.handles.lock().map_err(|_| Errno::EIO)?;
        let mut inodes = self.inodes.lock().map_err(|_| Errno::EIO)?;
        let source = child_path(self, &inodes, parent_inode, old_name)?;
        let destination = child_path(self, &inodes, new_parent_inode, new_name)?;
        if source == destination {
            return Ok(());
        }
        let source_scratch = self.resident.is_scratch(&source);
        let destination_scratch = self.resident.is_scratch(&destination);
        ensure_same_storage(source_scratch, destination_scratch).map_err(|_| Errno::EXDEV)?;
        let source_metadata = self.path_metadata(&source)?;
        validate_rename_target(&source, &destination)?;
        let destination_metadata = optional_metadata(self, &destination)?;
        let destination_empty =
            if destination_metadata.is_some_and(|metadata| metadata.kind == FileType::Directory) {
                self.entries_unlocked(&destination)?.is_empty()
            } else {
                true
            };
        validate_rename(
            source_metadata.kind,
            destination_metadata,
            destination_empty,
        )?;
        if source_metadata.kind == FileType::Directory {
            self.validate_directory_rename_storage(&source, &destination, source_scratch)?;
        }
        if source_scratch {
            self.scratch
                .rename(&source, &destination)
                .map_err(|error| errno("rename scratch path", &error))?;
        } else {
            handles.rename_resident(
                &source,
                &destination,
                |path| {
                    self.resident
                        .file(path)
                        .map(|file| file.bytes.to_vec())
                        .ok_or(Errno::ENOENT)
                },
                || {
                    self.resident
                        .rename(&source, &destination)
                        .map_err(|error| errno("rename resident path", &error))
                },
            )?;
        }
        inodes.move_path(&source, &destination);
        Ok(())
    }

    fn validate_directory_rename_storage(
        &self,
        source: &str,
        destination: &str,
        source_scratch: bool,
    ) -> Result<(), Errno> {
        let resident_paths = collect_descendants(source, |path| Ok(self.resident.entries(path)))?;
        let scratch_paths = collect_descendants(source, |path| {
            self.scratch
                .entries(path)
                .map_err(|error| errno("inspect scratch rename subtree", &error))
        })?;
        validate_subtree_storage(
            source,
            destination,
            source_scratch,
            &resident_paths,
            &scratch_paths,
            |path| self.resident.is_scratch(path),
        )
    }
}

fn optional_metadata(fs: &ResidentFuse, path: &str) -> Result<Option<PathMetadata>, Errno> {
    match fs.path_metadata(path) {
        Ok(metadata) => Ok(Some(metadata)),
        Err(error) if error.code() == libc::ENOENT => Ok(None),
        Err(error) => Err(error),
    }
}

fn validate_remove(kind: FileType, directory: bool) -> Result<(), Errno> {
    match (directory, kind) {
        (true, FileType::Directory) | (false, FileType::RegularFile) => Ok(()),
        (true, _) => Err(Errno::ENOTDIR),
        (false, FileType::Directory) => Err(Errno::EISDIR),
        (false, _) => Err(Errno::EINVAL),
    }
}

pub(super) fn validate_rename(
    source: FileType,
    destination: Option<PathMetadata>,
    destination_empty: bool,
) -> Result<(), Errno> {
    let Some(destination) = destination else {
        return Ok(());
    };
    match (source, destination.kind) {
        (FileType::RegularFile, FileType::Directory) => Err(Errno::EISDIR),
        (FileType::Directory, FileType::RegularFile) => Err(Errno::ENOTDIR),
        (FileType::Directory, FileType::Directory) if !destination_empty => Err(Errno::ENOTEMPTY),
        _ => Ok(()),
    }
}

pub(super) fn validate_rename_target(source: &str, destination: &str) -> Result<(), Errno> {
    if destination
        .strip_prefix(source)
        .is_some_and(|suffix| suffix.starts_with('/'))
    {
        return Err(Errno::EINVAL);
    }
    Ok(())
}

fn collect_descendants<F>(root: &str, mut entries: F) -> Result<Vec<String>, Errno>
where
    F: FnMut(&str) -> Result<Vec<(String, bool, u64)>, Errno>,
{
    let mut directories = vec![root.to_owned()];
    let mut paths = Vec::new();
    while let Some(directory) = directories.pop() {
        for (name, is_directory, _) in entries(&directory)? {
            let path = format!("{directory}/{name}");
            if is_directory {
                directories.push(path.clone());
            }
            paths.push(path);
        }
    }
    Ok(paths)
}

pub(super) fn validate_subtree_storage<F>(
    source: &str,
    destination: &str,
    source_scratch: bool,
    resident_paths: &[String],
    scratch_paths: &[String],
    is_scratch: F,
) -> Result<(), Errno>
where
    F: Fn(&str) -> bool,
{
    let (expected_paths, foreign_paths) = if source_scratch {
        (scratch_paths, resident_paths)
    } else {
        (resident_paths, scratch_paths)
    };
    if !foreign_paths.is_empty() {
        return Err(Errno::EXDEV);
    }
    for path in expected_paths {
        let suffix = path
            .strip_prefix(source)
            .filter(|suffix| suffix.starts_with('/'))
            .ok_or(Errno::EIO)?;
        let renamed = format!("{destination}{suffix}");
        if is_scratch(path) != source_scratch || is_scratch(&renamed) != source_scratch {
            return Err(Errno::EXDEV);
        }
    }
    Ok(())
}
