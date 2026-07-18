use std::collections::{BTreeMap, HashMap, HashSet};

use anyhow::Result;

use crate::model::{FileRecord, RecordSource};
use crate::paths::NormalizedPath;

use super::ResidentFile;

#[derive(Clone)]
pub(super) enum ChildEntry {
    Directory,
    File(ResidentFile),
}

impl ChildEntry {
    pub(super) fn is_directory(&self) -> bool {
        matches!(self, Self::Directory)
    }

    pub(super) fn file(&self) -> Option<&ResidentFile> {
        match self {
            Self::File(file) => Some(file),
            Self::Directory => None,
        }
    }
}

pub(super) fn build_children(
    files: &HashMap<NormalizedPath, ResidentFile>,
    directories: &HashSet<NormalizedPath>,
) -> HashMap<String, BTreeMap<String, ChildEntry>> {
    let mut children = HashMap::new();
    children.insert(String::new(), BTreeMap::new());
    for path in directories {
        insert_directory(&mut children, path.as_str());
    }
    for (path, file) in files {
        insert_file(&mut children, path.as_str(), file.clone());
    }
    children
}

pub(super) fn insert_directory(
    children: &mut HashMap<String, BTreeMap<String, ChildEntry>>,
    path: &str,
) {
    let (parent, name) = parent_and_name(path);
    children
        .entry(parent.to_owned())
        .or_default()
        .insert(name.to_owned(), ChildEntry::Directory);
    children.entry(path.to_owned()).or_default();
}

pub(super) fn insert_file(
    children: &mut HashMap<String, BTreeMap<String, ChildEntry>>,
    path: &str,
    file: ResidentFile,
) {
    let (parent, name) = parent_and_name(path);
    children
        .entry(parent.to_owned())
        .or_default()
        .insert(name.to_owned(), ChildEntry::File(file));
}

pub(super) fn remove_file(
    children: &mut HashMap<String, BTreeMap<String, ChildEntry>>,
    path: &str,
) {
    let (parent, name) = parent_and_name(path);
    if let Some(entries) = children.get_mut(parent) {
        entries.remove(name);
    }
}

pub(super) fn baseline_directories(
    baseline: &BTreeMap<NormalizedPath, FileRecord>,
) -> Result<HashSet<NormalizedPath>> {
    let mut directories = HashSet::new();
    for (path, record) in baseline {
        let mut current = String::new();
        let parts = path.as_str().split('/').collect::<Vec<_>>();
        let parent_count = if record.source == RecordSource::Directory {
            parts.len()
        } else {
            parts.len().saturating_sub(1)
        };
        for part in parts.into_iter().take(parent_count) {
            if !current.is_empty() {
                current.push('/');
            }
            current.push_str(part);
            directories.insert(NormalizedPath::parse_str(&current)?);
        }
    }
    Ok(directories)
}

fn parent_and_name(path: &str) -> (&str, &str) {
    path.rsplit_once('/').unwrap_or(("", path))
}
