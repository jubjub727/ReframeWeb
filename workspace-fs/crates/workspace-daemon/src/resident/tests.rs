#[cfg(test)]
mod tests {
    use super::*;

    fn empty_workspace() -> ResidentWorkspace {
        ResidentWorkspace {
            baseline: RwLock::new(BTreeMap::new()),
            files: RwLock::new(BTreeMap::new()),
            directories: RwLock::new(BTreeSet::new()),
            deleted: RwLock::new(BTreeSet::new()),
            scratch: ScratchMatcher::compile(std::iter::empty::<&str>()).unwrap(),
        }
    }

    #[test]
    fn resident_writes_are_sparse_and_reported() {
        let workspace = empty_workspace();
        workspace.write("notes/result.txt", 3, b"ok").unwrap();
        assert_eq!(
            &*workspace.file("notes/result.txt").unwrap().bytes,
            b"\0\0\0ok"
        );
        assert_eq!(workspace.changes()[0].kind, ChangeKind::Create);
    }

    #[test]
    fn duplicate_content_shares_one_allocation() {
        let bytes: Arc<[u8]> = Vec::from("shared").into();
        let left = ResidentFile { bytes: Arc::clone(&bytes), hash: "hash".into() };
        let right = ResidentFile { bytes: Arc::clone(&bytes), hash: "hash".into() };
        assert!(Arc::ptr_eq(&left.bytes, &right.bytes));
    }

    #[test]
    fn empty_directories_are_resident_and_checkpointable() {
        let workspace = empty_workspace();
        workspace.create_directory("empty/nested").unwrap();
        assert!(workspace.is_directory("empty/nested"));
        assert_eq!(workspace.changes().len(), 2);
        workspace.mark_checkpointed(&["empty".into(), "empty/nested".into()]).unwrap();
        assert!(workspace.changes().is_empty());
    }
}
