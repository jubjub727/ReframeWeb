use std::collections::HashMap;

use fuser::{Generation, INodeNo};

pub const ROOT_INODE: INodeNo = INodeNo(1);

#[derive(Debug)]
struct InodeEntry {
    path: String,
    generation: u64,
    lookup_count: u64,
    linked: bool,
}

pub struct InodeTable {
    next: u64,
    by_path: HashMap<String, INodeNo>,
    by_inode: HashMap<INodeNo, InodeEntry>,
}

impl InodeTable {
    pub fn new() -> Self {
        let mut table = Self {
            next: 2,
            by_path: HashMap::new(),
            by_inode: HashMap::new(),
        };
        table.insert(String::new(), ROOT_INODE);
        table
    }

    pub fn ensure(&mut self, path: &str) -> INodeNo {
        if let Some(inode) = self.by_path.get(path) {
            return *inode;
        }
        let inode = INodeNo(self.next);
        self.next = self.next.saturating_add(1);
        self.insert(path.to_owned(), inode);
        inode
    }

    pub fn inode_for_path(&self, path: &str) -> Option<INodeNo> {
        self.by_path.get(path).copied()
    }

    pub fn record_lookup(&mut self, path: &str) -> (INodeNo, Generation) {
        let inode = self.ensure(path);
        let entry = self
            .by_inode
            .get_mut(&inode)
            .expect("an inode created by ensure must have an entry");
        entry.lookup_count = entry.lookup_count.saturating_add(1);
        (inode, Generation(entry.generation))
    }

    pub fn path(&self, inode: INodeNo) -> Option<String> {
        self.by_inode
            .get(&inode)
            .filter(|entry| entry.linked)
            .map(|entry| entry.path.clone())
    }

    pub fn forget(&mut self, inode: INodeNo, count: u64) {
        if inode == ROOT_INODE {
            return;
        }
        let should_remove = self.by_inode.get_mut(&inode).is_some_and(|entry| {
            entry.lookup_count = entry.lookup_count.saturating_sub(count);
            !entry.linked && entry.lookup_count == 0
        });
        if should_remove {
            self.by_inode.remove(&inode);
        }
    }

    pub fn remove_path(&mut self, path: &str) {
        if path.is_empty() {
            return;
        }
        let prefix = format!("{path}/");
        let inodes = self
            .by_path
            .iter()
            .filter_map(|(candidate, inode)| {
                (candidate == path || candidate.starts_with(&prefix)).then_some(*inode)
            })
            .collect::<Vec<_>>();
        for inode in inodes {
            let Some(entry) = self.by_inode.get_mut(&inode) else {
                continue;
            };
            self.by_path.remove(&entry.path);
            entry.linked = false;
            if entry.lookup_count == 0 {
                self.by_inode.remove(&inode);
            }
        }
    }

    pub fn move_path(&mut self, source: &str, destination: &str) {
        self.remove_path(destination);
        let prefix = format!("{source}/");
        let moves = self
            .by_path
            .iter()
            .filter_map(|(path, inode)| {
                if path == source {
                    Some((path.clone(), destination.to_owned(), *inode))
                } else {
                    path.strip_prefix(&prefix)
                        .map(|relative| (path.clone(), format!("{destination}/{relative}"), *inode))
                }
            })
            .collect::<Vec<_>>();
        for (old, new, inode) in moves {
            self.by_path.remove(&old);
            self.by_path.insert(new.clone(), inode);
            if let Some(entry) = self.by_inode.get_mut(&inode) {
                entry.path = new;
            }
        }
    }

    fn insert(&mut self, path: String, inode: INodeNo) {
        self.by_path.insert(path.clone(), inode);
        self.by_inode.insert(
            inode,
            InodeEntry {
                path,
                generation: inode.0,
                lookup_count: 0,
                linked: true,
            },
        );
    }

    #[cfg(test)]
    fn retains_inode(&self, inode: INodeNo) -> bool {
        self.by_inode.contains_key(&inode)
    }
}

pub fn child(parent: &str, name: &std::ffi::OsStr) -> Option<String> {
    let name = name.to_str()?;
    if name.is_empty() || name.contains('/') || name == "." || name == ".." {
        return None;
    }
    Some(if parent.is_empty() {
        name.to_owned()
    } else {
        format!("{parent}/{name}")
    })
}

pub fn parent(path: &str) -> &str {
    path.rsplit_once('/')
        .map(|(parent, _)| parent)
        .unwrap_or("")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn removed_inode_survives_until_all_lookups_are_forgotten() {
        let mut table = InodeTable::new();
        let (inode, _) = table.record_lookup("dir/file.txt");
        table.record_lookup("dir/file.txt");

        table.remove_path("dir/file.txt");
        assert!(table.path(inode).is_none());
        assert!(table.retains_inode(inode));
        table.forget(inode, 1);
        assert!(table.retains_inode(inode));
        table.forget(inode, 1);
        assert!(!table.retains_inode(inode));
    }

    #[test]
    fn rename_overwrite_unlinks_the_old_destination_inode() {
        let mut table = InodeTable::new();
        let source = table.ensure("source.txt");
        let (destination, _) = table.record_lookup("destination.txt");

        table.move_path("source.txt", "destination.txt");

        assert_eq!(table.path(source).as_deref(), Some("destination.txt"));
        assert!(table.path(destination).is_none());
        assert_eq!(table.ensure("destination.txt"), source);
        table.forget(destination, 1);
        assert!(table.path(destination).is_none());
    }

    #[test]
    fn moving_a_directory_updates_descendant_paths() {
        let mut table = InodeTable::new();
        let child = table.ensure("old/nested/file.txt");
        table.move_path("old", "new");
        assert_eq!(table.path(child).as_deref(), Some("new/nested/file.txt"));
    }
}
