#[cfg(unix)]
mod unix {
    use std::io::ErrorKind;
    use std::os::unix::fs::PermissionsExt as _;

    use reframe_store_protocol::wire::Envelope;
    use reframe_store_transport::{
        FrameReader, FrameWriter, LocalEndpoint, LocalListener, connect,
    };

    #[tokio::test]
    async fn unix_socket_round_trip_is_private_and_removed_on_drop() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("store.sock");
        let endpoint = LocalEndpoint::from_path(&path).unwrap();
        let mut listener = LocalListener::bind(&endpoint).unwrap();
        assert_eq!(
            std::fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o600
        );

        let client = connect(&endpoint).await.unwrap();
        let server = listener.accept().await.unwrap();
        let exchange = async move {
            let (client_read, client_write) = tokio::io::split(client);
            let (server_read, server_write) = tokio::io::split(server);
            let mut client_writer = FrameWriter::new(client_write, 1024);
            let mut client_reader = FrameReader::new(client_read, 1024);
            let mut server_writer = FrameWriter::new(server_write, 1024);
            let mut server_reader = FrameReader::new(server_read, 1024);
            let envelope = Envelope {
                request_id: "round-trip".to_owned(),
                ..Envelope::default()
            };
            client_writer.write_envelope(&envelope).await.unwrap();
            let received = server_reader.read_envelope().await.unwrap().unwrap();
            server_writer.write_envelope(&received).await.unwrap();
            assert_eq!(client_reader.read_envelope().await.unwrap(), Some(envelope));
        };
        tokio::time::timeout(std::time::Duration::from_secs(2), exchange)
            .await
            .unwrap();

        drop(listener);
        assert!(!path.exists());
    }

    #[test]
    fn refuses_to_replace_an_active_socket() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("active.sock");
        let endpoint = LocalEndpoint::from_path(&path).unwrap();
        let _listener = LocalListener::bind(&endpoint).unwrap();

        let error = LocalListener::bind(&endpoint).unwrap_err();
        assert_eq!(error.kind(), ErrorKind::AddrInUse);
        assert!(path.exists());
    }

    #[test]
    fn safely_reclaims_only_stale_socket_files() {
        let directory = tempfile::tempdir().unwrap();
        let stale_path = directory.path().join("stale.sock");
        let stale = std::os::unix::net::UnixListener::bind(&stale_path).unwrap();
        drop(stale);
        let stale_endpoint = LocalEndpoint::from_path(&stale_path).unwrap();
        let replacement = LocalListener::bind(&stale_endpoint).unwrap();
        drop(replacement);

        let regular_path = directory.path().join("not-a-socket");
        std::fs::write(&regular_path, b"keep me").unwrap();
        let regular_endpoint = LocalEndpoint::from_path(&regular_path).unwrap();
        let error = LocalListener::bind(&regular_endpoint).unwrap_err();
        assert_eq!(error.kind(), ErrorKind::AlreadyExists);
        assert_eq!(std::fs::read(&regular_path).unwrap(), b"keep me");
    }
}

#[cfg(windows)]
mod windows {
    use reframe_store_transport::{LocalEndpoint, LocalListener, connect, connect_with_timeout};
    use tokio::io::{AsyncReadExt as _, AsyncWriteExt as _};

    #[tokio::test]
    async fn named_pipe_round_trip() {
        let endpoint = LocalEndpoint::for_service(&format!(
            "reframe-store-transport-test-{}",
            std::process::id()
        ))
        .unwrap();
        let mut listener = LocalListener::bind(&endpoint).unwrap();
        let mut client = connect(&endpoint).await.unwrap();
        let mut server = listener.accept().await.unwrap();
        client.write_all(b"ping").await.unwrap();
        let mut bytes = [0; 4];
        server.read_exact(&mut bytes).await.unwrap();
        assert_eq!(&bytes, b"ping");
    }

    #[tokio::test]
    async fn busy_named_pipe_connect_is_bounded() {
        let endpoint = LocalEndpoint::for_service(&format!(
            "reframe-store-transport-busy-test-{}",
            std::process::id()
        ))
        .unwrap();
        let _listener = LocalListener::bind(&endpoint).unwrap();
        let _first_client = connect(&endpoint).await.unwrap();

        let error = connect_with_timeout(&endpoint, std::time::Duration::from_millis(20))
            .await
            .unwrap_err();
        assert_eq!(error.kind(), std::io::ErrorKind::TimedOut);
    }
}
