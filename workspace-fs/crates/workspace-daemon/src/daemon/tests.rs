#[cfg(test)]
mod tests {
    use super::*;

    fn request(payload: &str) -> Request {
        serde_json::from_str(payload).unwrap()
    }

    #[test]
    fn mutating_operations_require_idempotency() -> Result<()> {
        let root = std::env::temp_dir().join(format!(
            "reframe-daemon-{}",
            crate::store::Store::next_id("test")
        ));
        let mut daemon = Daemon {
            store: Store::open(&root)?,
            residents: HashMap::new(),
            mounts: HashMap::new(),
        };
        let hello = daemon.handle(request(
            r#"{"request_id":"hello","operation":"hello"}"#,
        ));
        assert!(hello.ok);
        let create = daemon.handle(request(r#"{"request_id":"create","operation":"create_workspace","name":"test","session_id":"one","memory_sources":[],"scratch_paths":[]}"#));
        assert!(!create.ok);
        assert_eq!(create.error.unwrap().code, "idempotency_required");
        drop(daemon);
        std::fs::remove_dir_all(root)?;
        Ok(())
    }

    #[test]
    fn mutating_response_is_replayed_by_idempotency_key() -> Result<()> {
        let root = std::env::temp_dir().join(format!(
            "reframe-idempotency-{}",
            crate::store::Store::next_id("test")
        ));
        let mut daemon = Daemon {
            store: Store::open(&root)?,
            residents: HashMap::new(),
            mounts: HashMap::new(),
        };
        let payload = r#"{"request_id":"first","idempotency_key":"create-one","operation":"create_workspace","name":"test","session_id":"one","memory_sources":[],"scratch_paths":[]}"#;
        let first = daemon.handle(request(payload));
        let replay = daemon.handle(request(&payload.replace("first", "retry")));
        assert!(first.ok);
        assert_eq!(first.result, replay.result);
        assert_eq!(replay.request_id, "retry");
        drop(daemon);
        std::fs::remove_dir_all(root)?;
        Ok(())
    }
}
