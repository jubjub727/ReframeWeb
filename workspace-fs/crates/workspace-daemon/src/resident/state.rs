use std::collections::{BTreeMap, BTreeSet};

use anyhow::{Result, bail};

use crate::model::{Change, ChangeKind};
use crate::paths::NormalizedPath;

use super::{ResidentFile, ResidentState, add_parent_directories, has_prefix};

impl ResidentState {
    pub(super) fn replace_file(
        &mut self,
        path: NormalizedPath,
        bytes: Vec<u8>,
    ) -> Result<ChangeKind> {
        let kind = if self.baseline.contains_key(path.as_str()) {
            ChangeKind::Write
        } else {
            ChangeKind::Create
        };
        let hash = blake3::hash(&bytes).to_hex().to_string();
        self.files.insert(
            path.clone(),
            ResidentFile {
                bytes: bytes.into(),
                hash,
            },
        );
        self.directories.remove(path.as_str());
        add_parent_directories(&mut self.directories, path.as_str())?;
        Ok(kind)
    }

    pub(super) fn remove_path(&mut self, path: &NormalizedPath) {
        self.files
            .retain(|candidate, _| !same_or_descendant(candidate.as_str(), path.as_str()));
        self.directories
            .retain(|candidate| !same_or_descendant(candidate.as_str(), path.as_str()));
        self.rebuild_changes();
    }

    pub(super) fn rename_path(
        &mut self,
        source: &NormalizedPath,
        destination: &NormalizedPath,
    ) -> Result<()> {
        if has_prefix(destination.as_str(), source.as_str()) {
            bail!("cannot rename a path into itself: {source} -> {destination}");
        }
        let files = replacements(&self.files, source, destination)?;
        let directories = directory_replacements(&self.directories, source, destination)?;
        if files.is_empty() && directories.is_empty() {
            bail!("rename source does not exist: {source}");
        }
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
        add_parent_directories(&mut self.directories, destination.as_str())?;
        self.rebuild_changes();
        Ok(())
    }

    pub(super) fn rebuild_changes(&mut self) {
        let mut changes = BTreeMap::new();
        self.collect_file_changes(&mut changes);
        self.collect_directory_changes(&mut changes);
        self.collect_deletions(&mut changes);
        self.changes = changes;
    }

    fn collect_file_changes(&self, changes: &mut BTreeMap<NormalizedPath, Change>) {
        for (path, file) in &self.files {
            let kind = match self.baseline.get(path.as_str()) {
                None => Some(ChangeKind::Create),
                Some(original) if original.hash != file.hash => Some(ChangeKind::Write),
                _ => None,
            };
            if let Some(kind) = kind {
                changes.insert(
                    path.clone(),
                    Change {
                        path: path.to_string(),
                        kind,
                        size: Some(file.bytes.len() as u64),
                    },
                );
            }
        }
    }

    fn collect_directory_changes(&self, changes: &mut BTreeMap<NormalizedPath, Change>) {
        for path in &self.directories {
            let has_baseline_descendant = self
                .baseline
                .keys()
                .any(|candidate| has_prefix(candidate.as_str(), path.as_str()));
            if !self.baseline.contains_key(path.as_str()) && !has_baseline_descendant {
                changes.insert(
                    path.clone(),
                    Change {
                        path: path.to_string(),
                        kind: ChangeKind::Create,
                        size: None,
                    },
                );
            }
        }
    }

    fn collect_deletions(&self, changes: &mut BTreeMap<NormalizedPath, Change>) {
        for path in self.baseline.keys() {
            if !self.files.contains_key(path.as_str()) && !self.directories.contains(path.as_str())
            {
                changes.insert(
                    path.clone(),
                    Change {
                        path: path.to_string(),
                        kind: ChangeKind::Delete,
                        size: None,
                    },
                );
            }
        }
    }
}

fn replacements(
    files: &BTreeMap<NormalizedPath, ResidentFile>,
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
    directories: &BTreeSet<NormalizedPath>,
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
