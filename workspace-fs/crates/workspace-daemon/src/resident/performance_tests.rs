use std::hint::black_box;
use std::sync::atomic::{AtomicU64, AtomicUsize};
use std::sync::{Arc, RwLock};
use std::time::{Duration, Instant};

use anyhow::Result;

use crate::model::ChangeKind;
use crate::paths::ScratchMatcher;
use crate::store::VerifiedBlob;

use super::{ResidentFile, ResidentState, ResidentWorkspace};

const BENCHMARK_WINDOW: Duration = Duration::from_millis(75);

fn empty_workspace() -> ResidentWorkspace {
    ResidentWorkspace {
        state: RwLock::new(ResidentState::default()),
        scratch: ScratchMatcher::compile(std::iter::empty::<&str>()).unwrap(),
        file_count: AtomicUsize::new(0),
        byte_count: AtomicU64::new(0),
    }
}

#[test]
fn large_file_range_reads_return_only_the_requested_bytes() -> Result<()> {
    let bytes = (0..2 * 1024 * 1024)
        .map(|index| (index % 251) as u8)
        .collect::<Vec<_>>();
    let file = ResidentFile::owned(bytes.clone());
    let offset = bytes.len() - 73;

    assert_eq!(
        file.read_range(offset as u64, 64)?,
        bytes[offset..offset + 64]
    );
    assert!(file.read_range(bytes.len() as u64, 64)?.is_empty());
    Ok(())
}

#[test]
fn repeated_small_edits_preserve_large_file_content_and_one_dirty_entry() -> Result<()> {
    let workspace = empty_workspace();
    let mut expected = vec![b'a'; 1024 * 1024];
    workspace.replace("memory.md", expected.clone())?;

    for index in 0..256 {
        let offset = 257 + index * 1021;
        let replacement = [(index % 251) as u8; 17];
        workspace.write("memory.md", offset as u64, &replacement)?;
        expected[offset..offset + replacement.len()].copy_from_slice(&replacement);
    }

    assert_eq!(&*workspace.file("memory.md").unwrap().snapshot()?, expected);
    let changes = workspace.changes()?;
    assert_eq!(changes.len(), 1);
    assert_eq!(changes[0].kind, ChangeKind::Create);
    assert_eq!(changes[0].size, Some(expected.len() as u64));
    Ok(())
}

#[test]
fn indexed_listing_excludes_unrelated_workspace_files() -> Result<()> {
    let workspace = workspace_with_unrelated_files(512)?;
    let entries = workspace.entries("focus");
    let names = entries
        .iter()
        .map(|(name, _, _)| name.as_str())
        .collect::<Vec<_>>();

    assert_eq!(
        names,
        (0..16)
            .map(|index| format!("{index:02}.md"))
            .collect::<Vec<_>>()
    );
    assert!(
        entries
            .iter()
            .all(|(_, directory, size)| !directory && *size == 64)
    );
    Ok(())
}

#[test]
fn resident_stats_follow_in_place_size_changes() -> Result<()> {
    let workspace = empty_workspace();
    workspace.replace("one.md", vec![0; 1024])?;
    workspace.replace("two.md", vec![0; 2048])?;
    assert_eq!(workspace.stats().files, 2);
    assert_eq!(workspace.stats().bytes, 3072);

    workspace.write("one.md", 4096, &[1; 32])?;
    workspace.resize("two.md", 128)?;
    assert_eq!(workspace.stats().files, 2);
    assert_eq!(workspace.stats().bytes, 4096 + 32 + 128);

    workspace.remove("one.md")?;
    assert_eq!(workspace.stats().files, 1);
    assert_eq!(workspace.stats().bytes, 128);
    Ok(())
}

#[test]
fn unrelated_files_can_be_edited_concurrently() -> Result<()> {
    let workspace = Arc::new(empty_workspace());
    for worker in 0..8 {
        workspace.replace(&format!("worker-{worker}.txt"), vec![0; 4096])?;
    }

    std::thread::scope(|scope| {
        for worker in 0..8 {
            let workspace = Arc::clone(&workspace);
            scope.spawn(move || {
                let path = format!("worker-{worker}.txt");
                for offset in 0..512 {
                    workspace
                        .write(&path, offset * 8, &offset.to_le_bytes())
                        .unwrap();
                }
            });
        }
    });

    assert_eq!(workspace.changes()?.len(), 8);
    for worker in 0..8 {
        let bytes = workspace
            .file(&format!("worker-{worker}.txt"))
            .expect("worker file")
            .read_range(511 * 8, 8)?;
        assert_eq!(bytes, 511_u64.to_le_bytes());
    }
    Ok(())
}

#[test]
#[ignore = "manual resident hot-path algorithmic regression benchmark"]
fn benchmark_resident_hot_path_scaling() -> Result<()> {
    let small_file = ResidentFile::owned(vec![b'a'; 4 * 1024]);
    let large_file = ResidentFile::owned(vec![b'a'; 16 * 1024 * 1024]);
    let small_read = nanoseconds_per_operation(|| small_file.read_range(1024, 64).unwrap());
    let large_read = nanoseconds_per_operation(|| large_file.read_range(1024, 64).unwrap());

    let small_shared = VerifiedBlob::new(vec![b'a'; 4 * 1024].into());
    let large_shared = VerifiedBlob::new(vec![b'a'; 16 * 1024 * 1024].into());
    let small_first_write = nanoseconds_per_operation(|| {
        let file = ResidentFile::shared(small_shared.clone());
        file.write(1024, black_box(b"changed!")).unwrap()
    });
    let large_first_write = nanoseconds_per_operation(|| {
        let file = ResidentFile::shared(large_shared.clone());
        file.write(1024, black_box(b"changed!")).unwrap()
    });
    let small_truncate = nanoseconds_per_operation(|| {
        let file = ResidentFile::shared(small_shared.clone());
        file.resize(0).unwrap()
    });
    let large_truncate = nanoseconds_per_operation(|| {
        let file = ResidentFile::shared(large_shared.clone());
        file.resize(0).unwrap()
    });

    let small_edit = empty_workspace();
    small_edit.replace("hot.md", vec![b'a'; 4 * 1024])?;
    let large_edit = empty_workspace();
    large_edit.replace("hot.md", vec![b'a'; 16 * 1024 * 1024])?;
    let small_write = nanoseconds_per_operation(|| {
        small_edit
            .write("hot.md", 1024, black_box(b"changed!"))
            .unwrap()
    });
    let large_write = nanoseconds_per_operation(|| {
        large_edit
            .write("hot.md", 1024, black_box(b"changed!"))
            .unwrap()
    });

    let small_tree = workspace_with_unrelated_files(0)?;
    let large_tree = workspace_with_unrelated_files(4096)?;
    let small_listing = nanoseconds_per_operation(|| small_tree.entries("focus"));
    let large_listing = nanoseconds_per_operation(|| large_tree.entries("focus"));

    let small_mutations = workspace_with_unrelated_files(0)?;
    let large_mutations = workspace_with_unrelated_files(4096)?;
    let small_rename = nanoseconds_per_operation(|| {
        small_mutations
            .rename("focus/00.md", "focus/hot.md")
            .unwrap();
        small_mutations
            .rename("focus/hot.md", "focus/00.md")
            .unwrap();
    });
    let large_rename = nanoseconds_per_operation(|| {
        large_mutations
            .rename("focus/00.md", "focus/hot.md")
            .unwrap();
        large_mutations
            .rename("focus/hot.md", "focus/00.md")
            .unwrap();
    });
    let small_remove = nanoseconds_per_operation(|| {
        small_mutations
            .replace("focus/remove.md", vec![b'r'; 64])
            .unwrap();
        small_mutations.remove("focus/remove.md").unwrap();
    });
    let large_remove = nanoseconds_per_operation(|| {
        large_mutations
            .replace("focus/remove.md", vec![b'r'; 64])
            .unwrap();
        large_mutations.remove("focus/remove.md").unwrap();
    });

    report_ratio("read 64 B from 16 MiB vs 4 KiB", large_read, small_read);
    report_ratio(
        "first shared edit in 16 MiB vs 4 KiB",
        large_first_write,
        small_first_write,
    );
    report_ratio(
        "truncate shared 16 MiB vs 4 KiB",
        large_truncate,
        small_truncate,
    );
    report_ratio("edit 8 B in 16 MiB vs 4 KiB", large_write, small_write);
    report_ratio(
        "list with 4096 unrelated files vs none",
        large_listing,
        small_listing,
    );
    report_ratio(
        "rename one file with 4096 unrelated files vs none",
        large_rename,
        small_rename,
    );
    report_ratio(
        "create/remove one file with 4096 unrelated files vs none",
        large_remove,
        small_remove,
    );
    assert_ratio("range read", large_read, small_read, 8.0);
    assert_ratio(
        "first shared-file edit",
        large_first_write,
        small_first_write,
        8.0,
    );
    assert_ratio("shared-file truncate", large_truncate, small_truncate, 8.0);
    assert_ratio("repeated small edit", large_write, small_write, 12.0);
    assert_ratio(
        "indexed directory listing",
        large_listing,
        small_listing,
        8.0,
    );
    assert_ratio("single-file rename", large_rename, small_rename, 8.0);
    assert_ratio("single-file remove", large_remove, small_remove, 8.0);
    Ok(())
}

fn workspace_with_unrelated_files(count: usize) -> Result<ResidentWorkspace> {
    let workspace = empty_workspace();
    for index in 0..16 {
        workspace.replace(&format!("focus/{index:02}.md"), vec![b'f'; 64])?;
    }
    for index in 0..count {
        workspace.replace(&format!("unrelated/{index:05}.md"), vec![b'u'; 64])?;
    }
    Ok(workspace)
}

fn nanoseconds_per_operation<T>(mut operation: impl FnMut() -> T) -> f64 {
    let mut iterations = 1_u64;
    loop {
        let started = Instant::now();
        for _ in 0..iterations {
            black_box(operation());
        }
        let elapsed = started.elapsed();
        if elapsed >= BENCHMARK_WINDOW || iterations >= 1 << 30 {
            return elapsed.as_nanos() as f64 / iterations as f64;
        }
        iterations = iterations.saturating_mul(2);
    }
}

fn report_ratio(label: &str, large: f64, small: f64) {
    eprintln!(
        "{label}: {large:.0} ns / {small:.0} ns = {:.2}x",
        large / small
    );
}

fn assert_ratio(label: &str, large: f64, small: f64, limit: f64) {
    let ratio = large / small;
    assert!(
        ratio <= limit,
        "{label} scales by {ratio:.2}x; limit is {limit:.2}x"
    );
}
