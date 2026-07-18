#[cfg(test)]
mod tests {
    use std::collections::HashMap;
    use std::io::{Cursor, Read, Write};

    use anyhow::Result;

    use crate::daemon::Daemon;
    use crate::protocol::{IdempotencyScope, Request};
    use crate::store::Store;

    fn request(payload: &str) -> Request {
        serde_json::from_str(payload).unwrap()
    }

    struct TestStream {
        input: Cursor<Vec<u8>>,
        output: Vec<u8>,
    }

    impl TestStream {
        fn new(input: Vec<u8>) -> Self {
            Self {
                input: Cursor::new(input),
                output: Vec::new(),
            }
        }

        fn response(&self) -> crate::protocol::Response {
            let length = u32::from_le_bytes(self.output[..4].try_into().unwrap()) as usize;
            serde_json::from_slice(&self.output[4..4 + length]).unwrap()
        }
    }

    impl Read for TestStream {
        fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
            self.input.read(buffer)
        }
    }

    impl Write for TestStream {
        fn write(&mut self, buffer: &[u8]) -> std::io::Result<usize> {
            let count = buffer.len().min(3);
            self.output.extend_from_slice(&buffer[..count]);
            Ok(count)
        }

        fn flush(&mut self) -> std::io::Result<()> {
            Ok(())
        }
    }

    fn framed(payload: &[u8]) -> Vec<u8> {
        let mut frame = (payload.len() as u32).to_le_bytes().to_vec();
        frame.extend_from_slice(payload);
        frame
    }

    fn daemon(root: &std::path::Path) -> Result<Daemon> {
        Ok(Daemon {
            store: Store::open(root)?,
            content_cache: Default::default(),
            residents: HashMap::new(),
            process_idempotency_requests: Default::default(),
            mounts: HashMap::new(),
        })
    }

    #[test]
    fn mutating_operations_require_idempotency() -> Result<()> {
        let root = std::env::temp_dir().join(format!(
            "reframe-daemon-{}",
            crate::store::Store::next_id("test")
        ));
        let mut daemon = daemon(&root)?;
        let hello = daemon.handle(request(r#"{"request_id":"hello","operation":"hello"}"#));
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
        let mut daemon = daemon(&root)?;
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

    #[test]
    fn malformed_client_request_gets_a_structured_error() -> Result<()> {
        let root =
            std::env::temp_dir().join(format!("reframe-invalid-frame-{}", Store::next_id("test")));
        let mut daemon = daemon(&root)?;
        let mut stream = TestStream::new(framed(b"not-json"));

        let shutdown = super::super::transport::serve_connection(&mut daemon, &mut stream)?;
        let response = stream.response();

        assert!(!shutdown);
        assert!(!response.ok);
        assert_eq!(response.error.unwrap().code, "invalid_json");
        drop(daemon);
        std::fs::remove_dir_all(root)?;
        Ok(())
    }

    #[test]
    fn rejected_shutdown_does_not_stop_the_daemon() -> Result<()> {
        let root = std::env::temp_dir().join(format!(
            "reframe-rejected-shutdown-{}",
            Store::next_id("test")
        ));
        let mut daemon = daemon(&root)?;
        let mut stream =
            TestStream::new(framed(br#"{"request_id":"stop","operation":"shutdown"}"#));

        let shutdown = super::super::transport::serve_connection(&mut daemon, &mut stream)?;
        let response = stream.response();

        assert!(!shutdown);
        assert_eq!(response.error.unwrap().code, "idempotency_required");
        let health = daemon.handle(request(r#"{"request_id":"health","operation":"health"}"#));
        assert!(health.ok);
        drop(daemon);
        std::fs::remove_dir_all(root)?;
        Ok(())
    }

    #[test]
    fn reusing_a_key_for_different_arguments_is_rejected() -> Result<()> {
        let root = std::env::temp_dir().join(format!(
            "reframe-idempotency-conflict-{}",
            Store::next_id("test")
        ));
        let mut daemon = daemon(&root)?;
        let first = daemon.handle(request(r#"{"request_id":"first","idempotency_key":"same-key","operation":"create_workspace","name":"first","session_id":"one","memory_sources":[],"scratch_paths":[]}"#));
        let conflict = daemon.handle(request(r#"{"request_id":"second","idempotency_key":"same-key","operation":"create_workspace","name":"second","session_id":"two","memory_sources":[],"scratch_paths":[]}"#));

        assert!(first.ok);
        assert!(!conflict.ok);
        assert_eq!(conflict.error.unwrap().code, "idempotency_conflict");
        drop(daemon);
        std::fs::remove_dir_all(root)?;
        Ok(())
    }

    #[test]
    fn lifecycle_operations_use_process_local_idempotency() {
        let operations = [
            crate::protocol::Operation::MountWorkspace {
                session_id: "session".into(),
            },
            crate::protocol::Operation::Prefetch {
                session_id: "session".into(),
                paths: Vec::new(),
            },
            crate::protocol::Operation::UnmountWorkspace {
                session_id: "session".into(),
            },
            crate::protocol::Operation::Shutdown {},
        ];

        for operation in operations {
            assert!(operation.mutates());
            assert_eq!(
                operation.idempotency_scope(),
                IdempotencyScope::ProcessLocal
            );
        }
        for metadata in crate::protocol::OPERATIONS {
            assert_eq!(
                metadata.mutates,
                metadata.idempotency_scope != IdempotencyScope::None
            );
        }
    }

    #[test]
    fn mount_idempotency_reexecutes_after_daemon_reopen() -> Result<()> {
        let root =
            std::env::temp_dir().join(format!("reframe-mount-reopen-{}", Store::next_id("test")));
        let first_request = request(
            r#"{"request_id":"first","idempotency_key":"mount-one","operation":"mount_workspace","session_id":"one"}"#,
        );
        let mut first = daemon(&root)?;
        assert!(matches!(
            first.begin_idempotent(&first_request),
            super::super::idempotency::IdempotencyAction::Execute
        ));
        first.complete_idempotent(
            &first_request.operation,
            "mount-one",
            r#"{"request_id":"first","ok":true,"result":{"mount_path":"unused"}}"#,
        )?;
        drop(first);

        let connection = rusqlite::Connection::open(root.join("workspace.sqlite3"))?;
        let persisted: i64 = connection.query_row(
            "SELECT COUNT(*) FROM idempotency_responses WHERE key='mount-one'",
            [],
            |row| row.get(0),
        )?;
        assert_eq!(persisted, 0);
        drop(connection);

        let retry_request = request(
            r#"{"request_id":"retry","idempotency_key":"mount-one","operation":"mount_workspace","session_id":"one"}"#,
        );
        let mut reopened = daemon(&root)?;
        assert!(matches!(
            reopened.begin_idempotent(&retry_request),
            super::super::idempotency::IdempotencyAction::Execute
        ));
        drop(reopened);
        std::fs::remove_dir_all(root)?;
        Ok(())
    }
}
