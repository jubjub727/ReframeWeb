#[cfg(windows)]
use std::io::{Read, Write};
#[cfg(windows)]
use std::time::Duration;

use super::LocalListener;

fn root(label: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!(
        "reframe-local-{label}-{}-{}",
        std::process::id(),
        crate::store::Store::next_id("test")
    ))
}

#[test]
fn only_one_listener_can_own_a_store() {
    let root = root("listener");
    std::fs::create_dir_all(&root).unwrap();
    let first = LocalListener::bind(&root).unwrap();
    assert!(LocalListener::bind(&root).is_err());
    drop(first);
    let replacement = LocalListener::bind(&root).unwrap();
    drop(replacement);
    std::fs::remove_dir_all(root).unwrap();
}

#[cfg(windows)]
#[test]
fn stalled_named_pipe_read_honors_the_io_timeout() {
    let root = root("timeout");
    std::fs::create_dir_all(&root).unwrap();
    let listener = LocalListener::bind(&root).unwrap();
    let pipe = super::platform::pipe_name(&root);
    let server = std::thread::spawn(move || {
        let mut stream = listener.accept().unwrap();
        stream.set_io_timeout(Duration::from_millis(50)).unwrap();
        stream.read(&mut [0u8; 1]).unwrap_err().kind()
    });
    let client = connect(&pipe);
    assert_eq!(server.join().unwrap(), std::io::ErrorKind::TimedOut);
    drop(client);
    std::fs::remove_dir_all(root).unwrap();
}

#[cfg(windows)]
#[test]
fn named_pipe_delivers_consecutive_writes() {
    let root = root("writes");
    std::fs::create_dir_all(&root).unwrap();
    let listener = LocalListener::bind(&root).unwrap();
    let pipe = super::platform::pipe_name(&root);
    let server = std::thread::spawn(move || {
        let mut stream = listener.accept().unwrap();
        stream.write_all(&1055u32.to_le_bytes()).unwrap();
        stream.write_all(&vec![7u8; 1055]).unwrap();
    });
    let mut client = connect(&pipe);
    let mut header = [0u8; 4];
    client.read_exact(&mut header).unwrap();
    assert_eq!(u32::from_le_bytes(header), 1055);
    let mut payload = vec![0u8; 1055];
    client.read_exact(&mut payload).unwrap();
    assert!(payload.iter().all(|byte| *byte == 7));
    server.join().unwrap();
    drop(client);
    std::fs::remove_dir_all(root).unwrap();
}

#[cfg(windows)]
fn connect(pipe: &str) -> std::fs::File {
    loop {
        match std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .open(pipe)
        {
            Ok(client) => return client,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                std::thread::yield_now();
            }
            Err(error) => panic!("connect test pipe: {error}"),
        }
    }
}
