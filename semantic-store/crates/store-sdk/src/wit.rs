use std::{fs, io, path::PathBuf};

/// Directory containing the publishable canonical Semantic Store WIT package.
///
/// Guest and host build scripts should resolve bindings through this function
/// instead of assuming a workspace layout.
#[must_use]
pub fn semantic_store_wit_dir() -> &'static std::path::Path {
    std::path::Path::new(concat!(env!("CARGO_MANIFEST_DIR"), "/wit"))
}

/// Every canonical WIT source file in deterministic path order.
///
/// Binding build scripts should emit `cargo:rerun-if-changed` for each result so
/// edits below nested dependency directories are never missed.
pub fn semantic_store_wit_files() -> io::Result<Vec<PathBuf>> {
    let mut pending = vec![semantic_store_wit_dir().to_path_buf()];
    let mut files = Vec::new();
    while let Some(directory) = pending.pop() {
        let mut entries = fs::read_dir(directory)?.collect::<Result<Vec<_>, _>>()?;
        entries.sort_unstable_by_key(fs::DirEntry::file_name);
        for entry in entries {
            let file_type = entry.file_type()?;
            if file_type.is_dir() {
                pending.push(entry.path());
            } else if file_type.is_file() {
                files.push(entry.path());
            }
        }
    }
    files.sort_unstable();
    Ok(files)
}
