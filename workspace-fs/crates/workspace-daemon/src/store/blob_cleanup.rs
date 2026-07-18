use std::fs;

use anyhow::{Context, Result};

use super::Store;

impl Store {
    pub(crate) fn scavenge_orphan_blob_temporaries(&self) -> Result<usize> {
        let mut removed = 0;
        for prefix_entry in fs::read_dir(self.root.join("blobs"))? {
            let prefix_entry = prefix_entry?;
            if !prefix_entry.file_type()?.is_dir() {
                continue;
            }
            let Some(prefix) = prefix_entry.file_name().to_str().map(str::to_owned) else {
                continue;
            };
            if !valid_prefix(&prefix) {
                continue;
            }
            for entry in fs::read_dir(prefix_entry.path())? {
                let entry = entry?;
                if !entry.file_type()?.is_file() {
                    continue;
                }
                let Some(name) = entry.file_name().to_str().map(str::to_owned) else {
                    continue;
                };
                if orphan_temporary_name(&prefix, &name) {
                    fs::remove_file(entry.path()).with_context(|| {
                        format!("remove orphan blob temporary {}", entry.path().display())
                    })?;
                    removed += 1;
                }
            }
        }
        Ok(removed)
    }
}

fn valid_prefix(prefix: &str) -> bool {
    prefix.len() == 2 && prefix.bytes().all(lower_hex)
}

fn orphan_temporary_name(prefix: &str, name: &str) -> bool {
    let Some((hash, suffix)) = name.split_once(".tmp-") else {
        return false;
    };
    hash.len() == 64
        && hash.bytes().all(lower_hex)
        && &hash[..2] == prefix
        && suffix.len() == 36
        && uuid::Uuid::parse_str(suffix).is_ok()
}

fn lower_hex(byte: u8) -> bool {
    byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)
}

#[cfg(test)]
#[path = "blob_cleanup/tests.rs"]
mod tests;
