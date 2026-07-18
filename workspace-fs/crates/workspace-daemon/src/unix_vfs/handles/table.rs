use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs::File;
use std::sync::{Arc, Mutex, Weak};

use fuser::{Errno, FileHandle, INodeNo, OpenFlags};

use super::file::{OpenAccess, OpenHandle, ResidentFileState, SharedResidentFile};

pub(in crate::unix_vfs) struct OpenFileTable {
    next: u64,
    handles: HashMap<FileHandle, OpenHandle>,
    resident_files: HashMap<INodeNo, Weak<Mutex<ResidentFileState>>>,
    resident_paths: BTreeMap<String, INodeNo>,
}

impl OpenFileTable {
    pub(in crate::unix_vfs) fn new() -> Self {
        Self {
            next: 1,
            handles: HashMap::new(),
            resident_files: HashMap::new(),
            resident_paths: BTreeMap::new(),
        }
    }

    pub(in crate::unix_vfs) fn open_resident(
        &mut self,
        inode: INodeNo,
        path: &str,
        flags: OpenFlags,
    ) -> Result<FileHandle, Errno> {
        self.remove_closed_resident_files();
        let file = if let Some(file) = self.resident_files.get(&inode).and_then(Weak::upgrade) {
            let linked_path = file
                .lock()
                .map_err(|_| Errno::EIO)?
                .linked_path()
                .map(str::to_owned);
            if linked_path.as_deref() != Some(path) {
                return Err(Errno::EIO);
            }
            file
        } else {
            let file = Arc::new(Mutex::new(ResidentFileState::linked(path.to_owned())));
            self.resident_files.insert(inode, Arc::downgrade(&file));
            file
        };
        self.resident_paths.insert(path.to_owned(), inode);
        Ok(self.insert(OpenHandle::resident(
            inode,
            OpenAccess::from_flags(flags),
            file,
        )))
    }

    pub(in crate::unix_vfs) fn open_scratch(
        &mut self,
        inode: INodeNo,
        file: File,
        flags: OpenFlags,
    ) -> FileHandle {
        self.insert(OpenHandle::scratch(
            inode,
            OpenAccess::from_flags(flags),
            file,
        ))
    }

    pub(in crate::unix_vfs) fn get(
        &self,
        handle: FileHandle,
        inode: INodeNo,
    ) -> Result<OpenHandle, Errno> {
        self.handles
            .get(&handle)
            .filter(|entry| entry.inode() == inode)
            .cloned()
            .ok_or(Errno::EBADF)
    }

    pub(in crate::unix_vfs) fn release(
        &mut self,
        handle: FileHandle,
        inode: INodeNo,
    ) -> Result<(), Errno> {
        if self
            .handles
            .get(&handle)
            .is_none_or(|entry| entry.inode() != inode)
        {
            return Err(Errno::EBADF);
        }
        self.handles.remove(&handle);
        self.remove_closed_resident_files();
        Ok(())
    }

    pub(in crate::unix_vfs) fn unlink_resident<L, O>(
        &mut self,
        path: &str,
        mut load: L,
        operation: O,
    ) -> Result<(), Errno>
    where
        L: FnMut(&str) -> Result<Vec<u8>, Errno>,
        O: FnOnce() -> Result<(), Errno>,
    {
        let files = self.resident_files_in_subtrees(&[path]);
        let mut guards = lock_files(&files)?;
        let snapshots = guards
            .iter()
            .enumerate()
            .filter_map(|(index, file)| {
                file.linked_path()
                    .filter(|candidate| same_or_descendant(candidate, path))
                    .map(|candidate| (index, candidate.to_owned()))
            })
            .map(|(index, linked_path)| load(&linked_path).map(|bytes| (index, linked_path, bytes)))
            .collect::<Result<Vec<_>, _>>()?;
        for (index, _, bytes) in &snapshots {
            guards[*index].detach(bytes.clone());
        }
        if let Err(error) = operation() {
            for (index, linked_path, _) in snapshots {
                guards[index].relink(linked_path);
            }
            return Err(error);
        }
        for (_, linked_path, _) in snapshots {
            self.resident_paths.remove(&linked_path);
        }
        Ok(())
    }

    pub(in crate::unix_vfs) fn rename_resident<L, O>(
        &mut self,
        source: &str,
        destination: &str,
        mut load: L,
        operation: O,
    ) -> Result<(), Errno>
    where
        L: FnMut(&str) -> Result<Vec<u8>, Errno>,
        O: FnOnce() -> Result<(), Errno>,
    {
        if source == destination {
            return operation();
        }
        let files = self.resident_files_in_subtrees(&[source, destination]);
        let mut guards = lock_files(&files)?;
        let snapshots = guards
            .iter()
            .enumerate()
            .filter_map(|(index, file)| {
                file.linked_path()
                    .filter(|candidate| {
                        same_or_descendant(candidate, destination)
                            && !same_or_descendant(candidate, source)
                    })
                    .map(|candidate| (index, candidate.to_owned()))
            })
            .map(|(index, linked_path)| load(&linked_path).map(|bytes| (index, linked_path, bytes)))
            .collect::<Result<Vec<_>, _>>()?;
        for (index, _, bytes) in &snapshots {
            guards[*index].detach(bytes.clone());
        }
        if let Err(error) = operation() {
            for (index, linked_path, _) in snapshots {
                guards[index].relink(linked_path);
            }
            return Err(error);
        }
        for (index, linked_path, _) in &snapshots {
            debug_assert!(guards[*index].linked_path().is_none());
            self.resident_paths.remove(linked_path);
        }
        let source_moves = guards
            .iter()
            .enumerate()
            .filter_map(|(index, file)| {
                file.linked_path()
                    .and_then(|path| renamed_path(path, source, destination))
                    .map(|replacement| (index, replacement))
            })
            .collect::<Vec<_>>();
        for (index, replacement) in source_moves {
            let inode = files[index].0;
            if let Some(old_path) = guards[index].linked_path().map(str::to_owned) {
                self.resident_paths.remove(&old_path);
            }
            guards[index].relink(replacement.clone());
            self.resident_paths.insert(replacement, inode);
        }
        Ok(())
    }

    fn insert(&mut self, handle: OpenHandle) -> FileHandle {
        loop {
            let candidate = FileHandle(self.next);
            self.next = self.next.wrapping_add(1).max(1);
            if let std::collections::hash_map::Entry::Vacant(entry) = self.handles.entry(candidate)
            {
                entry.insert(handle);
                return candidate;
            }
        }
    }

    fn resident_files_in_subtrees(&mut self, roots: &[&str]) -> Vec<(INodeNo, SharedResidentFile)> {
        self.remove_closed_resident_files();
        let mut inodes = BTreeSet::new();
        for root in roots {
            self.add_subtree_inodes(root, &mut inodes);
        }
        inodes
            .into_iter()
            .filter_map(|inode| {
                self.resident_files
                    .get(&inode)
                    .and_then(Weak::upgrade)
                    .map(|file| (inode, file))
            })
            .collect()
    }

    fn add_subtree_inodes(&self, root: &str, inodes: &mut BTreeSet<INodeNo>) {
        if let Some(inode) = self.resident_paths.get(root) {
            inodes.insert(*inode);
        }
        let prefix = if root.is_empty() {
            String::new()
        } else {
            format!("{root}/")
        };
        for (path, inode) in self.resident_paths.range(prefix.clone()..) {
            if !path.starts_with(&prefix) {
                break;
            }
            inodes.insert(*inode);
        }
    }

    fn remove_closed_resident_files(&mut self) {
        let closed = self
            .resident_files
            .iter()
            .filter_map(|(inode, file)| (file.strong_count() == 0).then_some(*inode))
            .collect::<BTreeSet<_>>();
        self.resident_files
            .retain(|inode, _| !closed.contains(inode));
        self.resident_paths
            .retain(|_, inode| !closed.contains(inode));
    }

    #[cfg(test)]
    pub(super) fn resident_state(&self, inode: INodeNo) -> SharedResidentFile {
        self.resident_files
            .get(&inode)
            .and_then(Weak::upgrade)
            .expect("test resident handle must exist")
    }

    #[cfg(test)]
    pub(super) fn handle_count(&self) -> usize {
        self.handles.len()
    }
}

fn lock_files(
    files: &[(INodeNo, SharedResidentFile)],
) -> Result<Vec<std::sync::MutexGuard<'_, ResidentFileState>>, Errno> {
    files
        .iter()
        .map(|(_, file)| file.lock().map_err(|_| Errno::EIO))
        .collect()
}

fn renamed_path(path: &str, source: &str, destination: &str) -> Option<String> {
    if path == source {
        return Some(destination.to_owned());
    }
    path.strip_prefix(source)
        .and_then(|suffix| suffix.strip_prefix('/'))
        .map(|relative| format!("{destination}/{relative}"))
}

fn same_or_descendant(candidate: &str, path: &str) -> bool {
    candidate == path
        || candidate
            .strip_prefix(path)
            .is_some_and(|suffix| suffix.starts_with('/'))
}
