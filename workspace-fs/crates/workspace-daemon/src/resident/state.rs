use std::collections::{HashMap, HashSet};

use anyhow::{Result, bail};

use crate::model::{Change, ChangeKind};
use crate::paths::NormalizedPath;

use super::{ResidentFile, ResidentState, add_parent_directories, has_prefix, index};

impl ResidentState {
    pub(super) fn replace_file(
        &mut self,
        path: NormalizedPath,
        bytes: Vec<u8>,
    ) -> Result<(ChangeKind, usize, usize, bool)> {
        let kind = if self.baseline.contains_key(path.as_str()) {
            ChangeKind::Write
        } else {
            ChangeKind::Create
        };
        let (previous, current, inserted, file) = match self.files.get(path.as_str()) {
            Some(file) => {
                let (previous, current) = file.replace(bytes)?;
                file.mark_dirty();
                (previous, current, false, file.clone())
            }
            None => {
                let current = bytes.len();
                let file = ResidentFile::owned(bytes);
                self.files.insert(path.clone(), file.clone());
                (0, current, true, file)
            }
        };
        self.directories.remove(path.as_str());
        let inserted_directories = self.ensure_parent_directories(path.as_str())?;
        self.children.remove(path.as_str());
        index::insert_file(&mut self.children, path.as_str(), file);
        self.dirty.extend(inserted_directories);
        self.dirty.insert(path);
        Ok((kind, previous, current, inserted))
    }

    /// Returns removed file statistics when the operation used the constant-time
    /// single-file path. Directory removals return `None` so the caller can
    /// recount after the necessarily broader subtree mutation.
    pub(super) fn remove_path(&mut self, path: &NormalizedPath) -> Option<(usize, u64)> {
        if let Some(file) = self.files.remove(path.as_str()) {
            if self.baseline.contains_key(path.as_str()) {
                self.dirty.insert(path.clone());
            } else {
                self.dirty.remove(path.as_str());
            }
            index::remove_file(&mut self.children, path.as_str());
            return Some((1, file.len() as u64));
        }
        if !self.directories.contains(path.as_str()) {
            if self.baseline.contains_key(path.as_str()) {
                self.dirty.insert(path.clone());
            } else {
                self.dirty.remove(path.as_str());
            }
            return Some((0, 0));
        }
        self.mark_subtree_dirty(path);
        self.files
            .retain(|candidate, _| !same_or_descendant(candidate.as_str(), path.as_str()));
        self.directories
            .retain(|candidate| !same_or_descendant(candidate.as_str(), path.as_str()));
        self.children = index::build_children(&self.files, &self.directories);
        None
    }

    pub(super) fn rename_path(
        &mut self,
        source: &NormalizedPath,
        destination: &NormalizedPath,
    ) -> Result<Option<(usize, u64)>> {
        if has_prefix(destination.as_str(), source.as_str()) {
            bail!("cannot rename a path into itself: {source} -> {destination}");
        }
        if source == destination {
            if self.files.contains_key(source.as_str())
                || self.directories.contains(source.as_str())
            {
                return Ok(Some((0, 0)));
            }
            bail!("rename source does not exist: {source}");
        }
        if self.files.contains_key(source.as_str())
            && !self.directories.contains(destination.as_str())
        {
            return self.rename_file(source, destination).map(Some);
        }
        let files = replacements(&self.files, source, destination)?;
        let directories = directory_replacements(&self.directories, source, destination)?;
        if files.is_empty() && directories.is_empty() {
            bail!("rename source does not exist: {source}");
        }
        self.mark_subtree_dirty(source);
        self.mark_subtree_dirty(destination);
        self.files.retain(|path, _| {
            !same_or_descendant(path.as_str(), destination.as_str())
                && !same_or_descendant(path.as_str(), source.as_str())
        });
        self.directories.retain(|path| {
            !same_or_descendant(path.as_str(), destination.as_str())
                && !same_or_descendant(path.as_str(), source.as_str())
        });
        self.files.extend(files);
        self.directories.extend(directories);
        let inserted_directories = self.ensure_parent_directories(destination.as_str())?;
        self.dirty.extend(inserted_directories);
        self.mark_subtree_dirty(destination);
        self.children = index::build_children(&self.files, &self.directories);
        Ok(None)
    }

    pub(super) fn collect_changes(&mut self) -> Result<Vec<Change>> {
        let mut paths = self.dirty.iter().cloned().collect::<Vec<_>>();
        paths.sort();
        let evaluated = paths
            .into_iter()
            .map(|path| self.change_for(&path).map(|change| (path, change)))
            .collect::<Result<Vec<_>>>()?;
        let mut changes = Vec::new();
        for (path, change) in evaluated {
            if let Some(change) = change {
                changes.push(change);
            } else {
                self.dirty.remove(path.as_str());
                if let Some(file) = self.files.get(path.as_str()) {
                    file.mark_clean();
                }
            }
        }
        Ok(changes)
    }

    pub(super) fn refresh_baseline_directories(&mut self) -> Result<()> {
        self.baseline_directories = index::baseline_directories(&self.baseline)?;
        Ok(())
    }

    pub(super) fn ensure_parent_directories(&mut self, path: &str) -> Result<Vec<NormalizedPath>> {
        let mut parents = HashSet::new();
        add_parent_directories(&mut parents, path)?;
        let mut inserted = Vec::new();
        for parent in parents {
            if self.directories.insert(parent.clone()) {
                index::insert_directory(&mut self.children, parent.as_str());
                inserted.push(parent);
            }
        }
        Ok(inserted)
    }

    fn change_for(&self, path: &NormalizedPath) -> Result<Option<Change>> {
        if let Some(file) = self.files.get(path.as_str()) {
            let kind = match self.baseline.get(path.as_str()) {
                None => Some(ChangeKind::Create),
                Some(original) if original.hash != file.hash_hex()? => Some(ChangeKind::Write),
                _ => None,
            };
            return Ok(kind.map(|kind| Change {
                path: path.to_string(),
                kind,
                size: Some(file.len() as u64),
            }));
        }
        if self.directories.contains(path.as_str()) {
            let kind = match self.baseline.get(path.as_str()) {
                Some(record) if record.source == crate::model::RecordSource::Directory => None,
                Some(_) => Some(ChangeKind::Write),
                None if self.baseline_directories.contains(path.as_str()) => None,
                None => Some(ChangeKind::Create),
            };
            return Ok(kind.map(|kind| Change {
                path: path.to_string(),
                kind,
                size: None,
            }));
        }
        Ok(self.baseline.contains_key(path.as_str()).then(|| Change {
            path: path.to_string(),
            kind: ChangeKind::Delete,
            size: None,
        }))
    }

    fn mark_subtree_dirty(&mut self, root: &NormalizedPath) {
        self.dirty.insert(root.clone());
        self.dirty.extend(
            self.files
                .keys()
                .chain(self.directories.iter())
                .chain(self.baseline.keys())
                .filter(|path| same_or_descendant(path.as_str(), root.as_str()))
                .cloned()
                .collect::<Vec<_>>(),
        );
    }

    fn rename_file(
        &mut self,
        source: &NormalizedPath,
        destination: &NormalizedPath,
    ) -> Result<(usize, u64)> {
        let file = self
            .files
            .remove(source.as_str())
            .expect("single-file rename source was checked");
        index::remove_file(&mut self.children, source.as_str());
        let overwritten = self.files.remove(destination.as_str());
        if overwritten.is_some() {
            index::remove_file(&mut self.children, destination.as_str());
        }
        file.mark_dirty();
        self.files.insert(destination.clone(), file.clone());
        let inserted_directories = self.ensure_parent_directories(destination.as_str())?;
        index::insert_file(&mut self.children, destination.as_str(), file);
        self.dirty.insert(source.clone());
        self.dirty.insert(destination.clone());
        self.dirty.extend(inserted_directories);
        Ok(overwritten
            .map(|file| (1, file.len() as u64))
            .unwrap_or_default())
    }
}

fn replacements(
    files: &HashMap<NormalizedPath, ResidentFile>,
    source: &NormalizedPath,
    destination: &NormalizedPath,
) -> Result<Vec<(NormalizedPath, ResidentFile)>> {
    files
        .iter()
        .filter_map(|(path, file)| {
            rewritten_path(path, source, destination)
                .map(|path| path.map(|path| (path, file.clone())))
        })
        .collect()
}

fn directory_replacements(
    directories: &HashSet<NormalizedPath>,
    source: &NormalizedPath,
    destination: &NormalizedPath,
) -> Result<Vec<NormalizedPath>> {
    directories
        .iter()
        .filter_map(|path| rewritten_path(path, source, destination))
        .collect()
}

fn rewritten_path(
    path: &NormalizedPath,
    source: &NormalizedPath,
    destination: &NormalizedPath,
) -> Option<Result<NormalizedPath>> {
    if path == source {
        return Some(Ok(destination.clone()));
    }
    path.as_str()
        .strip_prefix(source.as_str())
        .and_then(|suffix| {
            suffix
                .strip_prefix('/')
                .map(|relative| NormalizedPath::parse_str(&format!("{destination}/{relative}")))
        })
}

fn same_or_descendant(candidate: &str, path: &str) -> bool {
    candidate == path || has_prefix(candidate, path)
}
