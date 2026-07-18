use std::fs;
use std::path::{Path, PathBuf};

use anyhow::Result;

use crate::model::RecordSource;
use crate::paths::ScratchMatcher;
use crate::resident::ContentCache;

use super::scan_source;

struct TestDirectory(PathBuf);

impl TestDirectory {
    fn new() -> Result<Self> {
        let path = std::env::temp_dir().join(format!(
            "reframe-parallel-source-scan-{}",
            uuid::Uuid::new_v4()
        ));
        fs::create_dir_all(&path)?;
        Ok(Self(path))
    }

    fn path(&self) -> &Path {
        &self.0
    }
}

impl Drop for TestDirectory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn parallel_source_scan_is_deterministic_and_populates_the_content_cache() -> Result<()> {
    let root = TestDirectory::new()?;
    let files = root.path().join("files");
    fs::create_dir_all(&files)?;
    fs::create_dir_all(root.path().join("ignored"))?;
    fs::write(root.path().join("ignored/skip.txt"), "not cached")?;

    let mut expected_bytes = 0;
    for index in (0..40).rev() {
        let bytes = format!("unique memory file {index}");
        expected_bytes += bytes.len();
        fs::write(files.join(format!("{index:02}.txt")), bytes)?;
    }

    let scratch = ScratchMatcher::compile(["ignored", "ignored/**"])?;
    let cache = ContentCache::new(expected_bytes + 1);
    let first = scan_source(root.path(), &scratch, Some(&cache))?;
    let second = scan_source(root.path(), &scratch, Some(&cache))?;

    assert_eq!(first, second);
    assert_eq!(first.len(), 41);
    assert_eq!(first[0].path.as_str(), "files");
    assert_eq!(first[0].source, RecordSource::Directory);
    assert!(first.windows(2).all(|pair| pair[0].path < pair[1].path));
    assert!(
        first
            .iter()
            .all(|record| !record.path.as_str().contains("ignored"))
    );
    assert_eq!(cache.stats(), (40, expected_bytes));
    for record in first
        .iter()
        .filter(|record| record.source != RecordSource::Directory)
    {
        let cached = cache
            .get(&record.hash)
            .expect("scanned file should be cached");
        assert_eq!(cached.bytes().len() as u64, record.size);
    }
    Ok(())
}
