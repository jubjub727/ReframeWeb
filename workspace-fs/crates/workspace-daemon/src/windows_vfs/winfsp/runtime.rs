use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, RwLock, Weak};

use winfsp_wrs_sys::{FSP_FSCTL_FILE_INFO, NTSTATUS};

use crate::resident::{RenameOutcome, ResidentFile, ResidentWorkspace};

use super::{info, status};

const FILE_DIRECTORY_FILE: u32 = 0x0000_0001;
const FILE_NON_DIRECTORY_FILE: u32 = 0x0000_0040;

pub(super) struct Runtime {
    resident: Arc<ResidentWorkspace>,
    handles: Mutex<Vec<Weak<Handle>>>,
    timestamp: u64,
    mounted: AtomicBool,
}

pub(super) struct Handle {
    path: RwLock<String>,
    kind: HandleKind,
    linked: AtomicBool,
}

enum HandleKind {
    ResidentFile(ResidentFile),
    ResidentDirectory,
    // A native scratch handle can be added here without changing callback ABI.
}

impl Runtime {
    pub(super) fn new(resident: Arc<ResidentWorkspace>) -> Self {
        Self {
            resident,
            handles: Mutex::new(Vec::new()),
            timestamp: filetime_now(),
            mounted: AtomicBool::new(false),
        }
    }

    pub(super) fn set_mounted(&self, mounted: bool) {
        self.mounted.store(mounted, Ordering::Release);
    }

    pub(super) fn is_mounted(&self) -> bool {
        self.mounted.load(Ordering::Acquire)
    }

    pub(super) fn volume_info(&self) -> winfsp_wrs_sys::FSP_FSCTL_VOLUME_INFO {
        info::volume(self.resident.stats().bytes)
    }

    pub(super) fn attributes(&self, path: &str) -> Result<u32, NTSTATUS> {
        let (_, is_directory, size) = self.lookup(path)?;
        Ok(info::file(path, is_directory, size, self.timestamp).FileAttributes)
    }

    pub(super) fn create(
        &self,
        path: &str,
        create_options: u32,
    ) -> Result<(Arc<Handle>, FSP_FSCTL_FILE_INFO), NTSTATUS> {
        if path.is_empty() || self.resident.contains_path(path) {
            return Err(status::OBJECT_NAME_COLLISION);
        }
        self.require_parent(path)?;
        let is_directory = create_options & FILE_DIRECTORY_FILE != 0;
        if is_directory {
            self.resident
                .create_directory(path)
                .map_err(status::mutation)?;
        } else {
            self.resident
                .replace(path, Vec::new())
                .map_err(status::mutation)?;
        }
        let handle = self.open_handle(path, is_directory)?;
        let file_info = self.handle_info(&handle)?;
        Ok((handle, file_info))
    }

    pub(super) fn open(
        &self,
        path: &str,
        create_options: u32,
    ) -> Result<(Arc<Handle>, FSP_FSCTL_FILE_INFO), NTSTATUS> {
        let (_, is_directory, _) = self.lookup(path)?;
        if create_options & FILE_DIRECTORY_FILE != 0 && !is_directory {
            return Err(status::NOT_A_DIRECTORY);
        }
        if create_options & FILE_NON_DIRECTORY_FILE != 0 && is_directory {
            return Err(status::FILE_IS_A_DIRECTORY);
        }
        let handle = self.open_handle(path, is_directory)?;
        let file_info = self.handle_info(&handle)?;
        Ok((handle, file_info))
    }

    pub(super) fn overwrite(&self, handle: &Handle) -> Result<FSP_FSCTL_FILE_INFO, NTSTATUS> {
        let path = handle.path()?;
        let HandleKind::ResidentFile(file) = &handle.kind else {
            return Err(status::FILE_IS_A_DIRECTORY);
        };
        self.resident
            .replace_open_file(&path, file, Vec::new())
            .map_err(status::mutation)?;
        self.handle_info(handle)
    }

    pub(super) fn read(
        &self,
        handle: &Handle,
        output: &mut [u8],
        offset: u64,
    ) -> Result<usize, NTSTATUS> {
        let HandleKind::ResidentFile(file) = &handle.kind else {
            return Err(status::FILE_IS_A_DIRECTORY);
        };
        if offset >= file.len() as u64 {
            return Err(status::END_OF_FILE);
        }
        file.copy_into(offset, output).map_err(status::mutation)
    }

    pub(super) fn write(
        &self,
        handle: &Handle,
        input: &[u8],
        offset: u64,
        append: bool,
        constrained: bool,
    ) -> Result<(usize, FSP_FSCTL_FILE_INFO), NTSTATUS> {
        let HandleKind::ResidentFile(file) = &handle.kind else {
            return Err(status::FILE_IS_A_DIRECTORY);
        };
        let path = handle.path()?;
        let offset = if append { file.len() as u64 } else { offset };
        let input = if constrained {
            let start = usize::try_from(offset).map_err(|_| status::INVALID_PARAMETER)?;
            if start >= file.len() {
                &[]
            } else {
                &input[..input.len().min(file.len() - start)]
            }
        } else {
            input
        };
        if !input.is_empty() {
            self.resident
                .write_open_file(&path, file, offset, input)
                .map_err(status::mutation)?;
        }
        Ok((input.len(), self.handle_info(handle)?))
    }

    pub(super) fn resize(
        &self,
        handle: &Handle,
        size: u64,
        allocation_only: bool,
    ) -> Result<FSP_FSCTL_FILE_INFO, NTSTATUS> {
        let HandleKind::ResidentFile(file) = &handle.kind else {
            return Err(status::FILE_IS_A_DIRECTORY);
        };
        let path = handle.path()?;
        if !allocation_only || size < file.len() as u64 {
            self.resident
                .resize_open_file(&path, file, size)
                .map_err(status::mutation)?;
        }
        self.handle_info(handle)
    }

    pub(super) fn rename(
        &self,
        source: &str,
        destination: &str,
        replace: bool,
    ) -> Result<(), NTSTATUS> {
        if destination.is_empty() {
            return Err(status::ACCESS_DENIED);
        }
        self.require_parent(destination)?;
        let outcome = self
            .resident
            .rename_with_replace(source, destination, replace)
            .map_err(status::mutation)?;
        self.mark_replaced_handles(destination, &outcome)?;
        self.rewrite_open_paths(source, destination)?;
        Ok(())
    }

    pub(super) fn can_delete(&self, handle: &Handle) -> Result<(), NTSTATUS> {
        if !handle.is_linked() {
            return Ok(());
        }
        let path = handle.path()?;
        if path.is_empty() {
            return Err(status::ACCESS_DENIED);
        }
        if handle.is_directory() && !self.resident.entries(&path).is_empty() {
            return Err(status::DIRECTORY_NOT_EMPTY);
        }
        Ok(())
    }

    pub(super) fn delete(&self, handle: &Handle) -> Result<(), NTSTATUS> {
        self.can_delete(handle)?;
        if !handle.is_linked() {
            return Ok(());
        }
        let path = handle.path()?;
        match &handle.kind {
            HandleKind::ResidentFile(file) => {
                self.resident
                    .remove_open_file(&path, file)
                    .map_err(status::mutation)?;
            }
            HandleKind::ResidentDirectory => {
                self.resident.remove(&path).map_err(status::mutation)?;
            }
        }
        self.mark_node_unlinked(handle)
    }

    pub(super) fn handle_info(&self, handle: &Handle) -> Result<FSP_FSCTL_FILE_INFO, NTSTATUS> {
        let path = handle.path()?;
        let size = match &handle.kind {
            HandleKind::ResidentFile(file) => file.len() as u64,
            HandleKind::ResidentDirectory => 0,
        };
        Ok(info::file(
            &path,
            handle.is_directory(),
            size,
            self.timestamp,
        ))
    }

    pub(super) fn visit_directory_entries(
        &self,
        handle: &Handle,
        marker: Option<&str>,
        mut visitor: impl FnMut(&str, FSP_FSCTL_FILE_INFO) -> bool,
    ) -> Result<bool, NTSTATUS> {
        if !handle.is_directory() {
            return Err(status::NOT_A_DIRECTORY);
        }
        let path = handle.path()?;
        if !path.is_empty() {
            if after_marker(".", marker) && !visitor(".", self.handle_info(handle)?) {
                return Ok(false);
            }
            let parent = path.rsplit_once('/').map_or("", |(parent, _)| parent);
            if after_marker("..", marker) {
                let (_, is_directory, size) = self.lookup(parent)?;
                if !visitor("..", info::file(parent, is_directory, size, self.timestamp)) {
                    return Ok(false);
                }
            }
        }
        if !handle.is_linked() {
            return Ok(true);
        }
        self.resident
            .visit_entries_after(&path, marker, |name, is_directory, size| {
                let child = if path.is_empty() {
                    name.to_owned()
                } else {
                    format!("{path}/{name}")
                };
                visitor(name, info::file(&child, is_directory, size, self.timestamp))
            })
            .map_err(status::mutation)
    }

    fn lookup(&self, path: &str) -> Result<(Option<ResidentFile>, bool, u64), NTSTATUS> {
        if path.is_empty() || self.resident.is_directory(path) {
            return Ok((None, true, 0));
        }
        let file = self
            .resident
            .file(path)
            .ok_or(status::OBJECT_NAME_NOT_FOUND)?;
        let size = file.len() as u64;
        Ok((Some(file), false, size))
    }

    fn open_handle(&self, path: &str, is_directory: bool) -> Result<Arc<Handle>, NTSTATUS> {
        let kind = if is_directory {
            HandleKind::ResidentDirectory
        } else {
            HandleKind::ResidentFile(
                self.resident
                    .file(path)
                    .ok_or(status::OBJECT_NAME_NOT_FOUND)?,
            )
        };
        let handle = Arc::new(Handle {
            path: RwLock::new(path.to_owned()),
            kind,
            linked: AtomicBool::new(true),
        });
        let mut handles = self.handles.lock().map_err(|_| status::INTERNAL_ERROR)?;
        handles.retain(|handle| handle.strong_count() != 0);
        handles.push(Arc::downgrade(&handle));
        Ok(handle)
    }

    fn require_parent(&self, path: &str) -> Result<(), NTSTATUS> {
        let parent = path.rsplit_once('/').map_or("", |(parent, _)| parent);
        if self.resident.is_directory(parent) {
            Ok(())
        } else {
            Err(status::OBJECT_PATH_NOT_FOUND)
        }
    }

    fn rewrite_open_paths(&self, source: &str, destination: &str) -> Result<(), NTSTATUS> {
        let mut handles = self.handles.lock().map_err(|_| status::INTERNAL_ERROR)?;
        handles.retain(|weak| {
            let Some(handle) = weak.upgrade() else {
                return false;
            };
            if !handle.is_linked() {
                return true;
            }
            let Ok(mut path) = handle.path.write() else {
                return true;
            };
            if *path == source {
                *path = destination.to_owned();
            } else if let Some(suffix) = path.strip_prefix(source).and_then(|p| p.strip_prefix('/'))
            {
                *path = format!("{destination}/{suffix}");
            }
            true
        });
        Ok(())
    }

    fn mark_replaced_handles(
        &self,
        destination: &str,
        outcome: &RenameOutcome,
    ) -> Result<(), NTSTATUS> {
        let mut handles = self.handles.lock().map_err(|_| status::INTERNAL_ERROR)?;
        handles.retain(|weak| {
            let Some(handle) = weak.upgrade() else {
                return false;
            };
            let replaced = match (&handle.kind, &outcome.replaced_file) {
                (HandleKind::ResidentFile(file), Some(replaced)) => file.same_identity(replaced),
                (HandleKind::ResidentDirectory, _) if outcome.replaced_directory => {
                    handle.path().is_ok_and(|path| path == destination)
                }
                _ => false,
            };
            if replaced {
                handle.unlink();
            }
            true
        });
        Ok(())
    }

    fn mark_node_unlinked(&self, target: &Handle) -> Result<(), NTSTATUS> {
        let target_path = target.path()?;
        let mut handles = self.handles.lock().map_err(|_| status::INTERNAL_ERROR)?;
        handles.retain(|weak| {
            let Some(handle) = weak.upgrade() else {
                return false;
            };
            let same_node = match (&handle.kind, &target.kind) {
                (HandleKind::ResidentFile(left), HandleKind::ResidentFile(right)) => {
                    left.same_identity(right)
                }
                (HandleKind::ResidentDirectory, HandleKind::ResidentDirectory) => {
                    handle.path().is_ok_and(|path| path == target_path)
                }
                _ => false,
            };
            if same_node {
                handle.unlink();
            }
            true
        });
        Ok(())
    }
}

impl Handle {
    pub(super) fn path(&self) -> Result<String, NTSTATUS> {
        self.path
            .read()
            .map(|path| path.clone())
            .map_err(|_| status::INTERNAL_ERROR)
    }

    pub(super) fn is_directory(&self) -> bool {
        matches!(self.kind, HandleKind::ResidentDirectory)
    }

    fn is_linked(&self) -> bool {
        self.linked.load(Ordering::Acquire)
    }

    fn unlink(&self) {
        self.linked.store(false, Ordering::Release);
    }
}

fn after_marker(name: &str, marker: Option<&str>) -> bool {
    marker.is_none_or(|marker| name > marker)
}

fn filetime_now() -> u64 {
    const WINDOWS_TO_UNIX_SECONDS: u64 = 11_644_473_600;
    let unix = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default();
    (unix.as_secs() + WINDOWS_TO_UNIX_SECONDS) * 10_000_000 + u64::from(unix.subsec_nanos() / 100)
}

#[cfg(test)]
mod tests {
    use super::Runtime;
    use crate::resident::ResidentWorkspace;
    use crate::windows_vfs::winfsp::status;

    #[test]
    fn surviving_deleted_handle_never_recreates_or_mutates_the_path() {
        let resident = ResidentWorkspace::empty_for_test();
        resident.replace("memory.md", b"old".to_vec()).unwrap();
        let runtime = Runtime::new(resident.clone());
        let (deleting, _) = runtime.open("memory.md", 0).unwrap();
        let (survivor, _) = runtime.open("memory.md", 0).unwrap();

        runtime.delete(&deleting).unwrap();
        assert!(!resident.contains_file("memory.md"));
        runtime.write(&survivor, b"X", 0, false, false).unwrap();
        assert!(!resident.contains_file("memory.md"));

        resident.replace("memory.md", b"new".to_vec()).unwrap();
        runtime.write(&survivor, b"Y", 0, false, false).unwrap();
        assert_eq!(
            resident
                .file("memory.md")
                .expect("recreated file")
                .snapshot()
                .unwrap()
                .as_ref(),
            b"new"
        );
        let mut old_bytes = [0; 3];
        assert_eq!(runtime.read(&survivor, &mut old_bytes, 0).unwrap(), 3);
        assert_eq!(&old_bytes, b"Yld");
    }

    #[test]
    fn replaced_destination_handle_cannot_mutate_the_renamed_file() {
        let resident = ResidentWorkspace::empty_for_test();
        resident.replace("source", b"source".to_vec()).unwrap();
        resident
            .replace("destination", b"old-destination".to_vec())
            .unwrap();
        let runtime = Runtime::new(resident.clone());
        let (old_destination, _) = runtime.open("destination", 0).unwrap();

        runtime.rename("source", "destination", true).unwrap();
        runtime
            .write(&old_destination, b"X", 0, false, false)
            .unwrap();
        runtime.delete(&old_destination).unwrap();

        assert_eq!(
            resident
                .file("destination")
                .expect("renamed source")
                .snapshot()
                .unwrap()
                .as_ref(),
            b"source"
        );
        let mut old_bytes = [0; 3];
        assert_eq!(
            runtime.read(&old_destination, &mut old_bytes, 0).unwrap(),
            3
        );
        assert_eq!(&old_bytes, b"Xld");
    }

    #[test]
    fn replacement_rename_rejects_type_changes_and_nonempty_directories() {
        let resident = ResidentWorkspace::empty_for_test();
        let runtime = Runtime::new(resident.clone());

        resident.replace("file", b"file".to_vec()).unwrap();
        resident.create_directory("directory/child").unwrap();
        assert_eq!(
            runtime.rename("file", "directory", true),
            Err(status::FILE_IS_A_DIRECTORY)
        );
        assert!(resident.contains_file("file"));
        assert!(resident.is_directory("directory/child"));

        resident.create_directory("directory-source").unwrap();
        resident
            .replace("file-destination", b"file".to_vec())
            .unwrap();
        assert_eq!(
            runtime.rename("directory-source", "file-destination", true),
            Err(status::NOT_A_DIRECTORY)
        );
        assert!(resident.is_directory("directory-source"));
        assert!(resident.contains_file("file-destination"));

        resident.create_directory("tree-source").unwrap();
        resident.create_directory("tree-destination/child").unwrap();
        assert_eq!(
            runtime.rename("tree-source", "tree-destination", true),
            Err(status::DIRECTORY_NOT_EMPTY)
        );
        assert!(resident.is_directory("tree-source"));
        assert!(resident.is_directory("tree-destination/child"));

        resident.replace("left", b"left".to_vec()).unwrap();
        resident.replace("right", b"right".to_vec()).unwrap();
        assert_eq!(
            runtime.rename("left", "right", false),
            Err(status::OBJECT_NAME_COLLISION)
        );
        assert!(resident.contains_file("left"));
        assert!(resident.contains_file("right"));
    }
}
