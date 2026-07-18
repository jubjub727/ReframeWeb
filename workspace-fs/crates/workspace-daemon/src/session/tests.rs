#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    fn temp_root(label: &str) -> PathBuf {
        std::env::temp_dir().join(format!("reframe-{label}-{}", Store::next_id("test")))
    }

    #[test]
    fn memory_edit_checkpoint_and_resume_round_trip() -> Result<()> {
        let root = temp_root("roundtrip");
        let memory = root.join("manual-memory");
        fs::create_dir_all(memory.join("notes"))?;
        fs::create_dir_all(memory.join(".git/objects"))?;
        fs::create_dir_all(memory.join(".reframe-memory-smoke/data"))?;
        fs::create_dir_all(memory.join(".venv/Lib"))?;
        fs::write(memory.join("notes/brief.md"), "initial")?;
        fs::write(memory.join(".git/objects/internal"), "ignored")?;
        fs::write(memory.join(".reframe-memory-smoke/data/store"), "ignored")?;
        fs::write(memory.join(".venv/Lib/package.py"), "ignored")?;
        let mut store = Store::open(&root.join("store"))?;
        store.persist_memory_source("memory_node:brief", &memory)?;
        let created = create(
            &mut store,
            "first",
            Some("first"),
            &["memory_node:brief".into()],
            &[],
        )?;
        let first_baseline = baseline(&store, "first")?;
        assert_eq!(first_baseline["notes/brief.md"].source_kind, "memory");
        assert!(!first_baseline.contains_key(".git/objects/internal"));
        assert!(!first_baseline.contains_key(".reframe-memory-smoke/data/store"));
        assert!(!first_baseline.contains_key(".venv/Lib/package.py"));

        let worktree = PathBuf::from(created.worktree);
        fs::create_dir_all(worktree.join("notes"))?;
        fs::write(worktree.join("notes/brief.md"), "changed")?;
        fs::write(worktree.join("answer.txt"), "retained")?;
        let changes = scan_changes(&mut store, "first")?;
        assert_eq!(changes.len(), 2);
        let result = checkpoint(&mut store, "first", &[PathBuf::from("answer.txt")], false)?;
        assert_eq!(result.retained_paths, ["answer.txt"]);
        assert_eq!(result.remaining_changes.len(), 1);

        store.persist_checkpoint_source(
            "memory_node:checkpoint-one",
            store.root(),
            &result.manifest_id,
        )?;
        store.persist_checkpoint_source(
            "memory_node:checkpoint-alias",
            store.root(),
            &result.manifest_id,
        )?;
        let resumed = create(
            &mut store,
            "second",
            Some("second"),
            &["memory_node:checkpoint-one".into()],
            &[],
        )?;
        assert_eq!(
            baseline(&store, "second")?["answer.txt"].source_kind,
            "backing_blob"
        );
        assert_eq!(resumed.projected_files, 1);
        let aliased = create(
            &mut store,
            "third",
            Some("third"),
            &["memory_node:checkpoint-alias".into()],
            &[],
        )?;
        assert_eq!(aliased.projected_files, 1);
        drop(store);
        std::thread::sleep(Duration::from_millis(5));
        fs::remove_dir_all(root)?;
        Ok(())
    }

    #[test]
    fn configured_scratch_glob_never_enters_the_journal() -> Result<()> {
        let root = temp_root("scratch-glob");
        let mut store = Store::open(&root.join("store"))?;
        let created = create(
            &mut store,
            "scratch",
            Some("scratch"),
            &[],
            &[PathBuf::from("generated/**")],
        )?;
        let worktree = PathBuf::from(created.worktree);
        fs::create_dir_all(worktree.join("generated/nested"))?;
        fs::write(worktree.join("generated/nested/cache.bin"), "discard")?;
        fs::write(worktree.join("answer.txt"), "retain")?;

        let changes = scan_changes(&mut store, "scratch")?;

        assert_eq!(changes.len(), 1);
        assert_eq!(changes[0].path, "answer.txt");
        drop(store);
        fs::remove_dir_all(root)?;
        Ok(())
    }

    #[test]
    fn closed_session_cannot_be_reopened_for_work() -> Result<()> {
        let root = temp_root("closed-session");
        let mut store = Store::open(&root.join("store"))?;
        create(&mut store, "closed", Some("closed"), &[], &[])?;

        close(&store, "closed")?;

        assert!(ensure_active(&store, "closed").is_err());
        assert!(list(&store, true)?.is_empty());
        let sessions = list(&store, false)?;
        assert_eq!(sessions.len(), 1);
        assert_eq!(sessions[0].session_id, "closed");
        drop(store);
        fs::remove_dir_all(root)?;
        Ok(())
    }

    #[test]
    fn resident_empty_directory_survives_checkpoint_and_resume() -> Result<()> {
        let root = temp_root("empty-directory");
        let mut store = Store::open(&root.join("store"))?;
        create(&mut store, "first", Some("first"), &[], &[])?;
        let resident = crate::resident::ResidentWorkspace::load(&store, "first")?;
        resident.create_directory("results/empty")?;
        replace_journal(&mut store, "first", &resident.changes())?;

        let checkpoint = checkpoint_resident(&mut store, "first", &[], true, &resident)?;
        let entries = manifest_entries(&store, &checkpoint.manifest_id)?;
        assert!(entries.iter().any(|entry| {
            entry.path == "results/empty" && entry.source_kind == "directory"
        }));

        store.persist_checkpoint_source(
            "memory_node:directory-checkpoint",
            store.root(),
            &checkpoint.manifest_id,
        )?;
        create(
            &mut store,
            "second",
            Some("second"),
            &["memory_node:directory-checkpoint".into()],
            &[],
        )?;
        let resumed = crate::resident::ResidentWorkspace::load(&store, "second")?;
        assert!(resumed.is_directory("results/empty"));

        drop(store);
        fs::remove_dir_all(root)?;
        Ok(())
    }
}
