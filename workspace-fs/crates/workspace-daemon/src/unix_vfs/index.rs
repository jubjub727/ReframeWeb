use std::collections::HashMap;

use fuser::INodeNo;

pub const ROOT_INODE: INodeNo = INodeNo(1);

pub struct InodeTable {
    next: u64,
    by_path: HashMap<String, INodeNo>,
    by_inode: HashMap<INodeNo, String>,
}

impl InodeTable {
    pub fn new() -> Self {
        let mut table = Self {
            next: 2,
            by_path: HashMap::new(),
            by_inode: HashMap::new(),
        };
        table.by_path.insert(String::new(), ROOT_INODE);
        table.by_inode.insert(ROOT_INODE, String::new());
        table
    }

    pub fn ensure(&mut self, path: &str) -> INodeNo {
        if let Some(inode) = self.by_path.get(path) {
            return *inode;
        }
        let inode = INodeNo(self.next);
        self.next += 1;
        self.by_path.insert(path.to_owned(), inode);
        self.by_inode.insert(inode, path.to_owned());
        inode
    }

    pub fn path(&self, inode: INodeNo) -> Option<String> {
        self.by_inode.get(&inode).cloned()
    }

    pub fn move_path(&mut self, source: &str, destination: &str) {
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
            self.by_inode.insert(inode, new);
        }
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
