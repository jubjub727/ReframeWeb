use std::fs::{File, OpenOptions};
use std::io::{Error, ErrorKind, Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{FileTypeExt, MetadataExt, OpenOptionsExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

pub struct LocalListener {
    listener: UnixListener,
    endpoint: PathBuf,
    endpoint_identity: (u64, u64),
    _lock: StoreLock,
}

pub struct StoreLock {
    _file: File,
}

impl LocalListener {
    pub fn bind(store: &Path) -> std::io::Result<Self> {
        let lock = StoreLock::acquire(store)?;
        let endpoint = store.join("workspace-daemon.sock");
        prepare_endpoint(&endpoint)?;
        let listener = UnixListener::bind(&endpoint)?;
        if let Err(error) =
            std::fs::set_permissions(&endpoint, std::fs::Permissions::from_mode(0o600))
        {
            drop(listener);
            let _ = std::fs::remove_file(&endpoint);
            return Err(error);
        }
        let metadata = std::fs::metadata(&endpoint)?;
        Ok(Self {
            listener,
            endpoint,
            endpoint_identity: (metadata.dev(), metadata.ino()),
            _lock: lock,
        })
    }

    pub fn accept(&self) -> std::io::Result<LocalStream> {
        self.listener
            .accept()
            .map(|(stream, _)| LocalStream(stream))
    }
}

impl Drop for LocalListener {
    fn drop(&mut self) {
        let owned_endpoint = std::fs::metadata(&self.endpoint)
            .map(|metadata| (metadata.dev(), metadata.ino()) == self.endpoint_identity)
            .unwrap_or(false);
        if owned_endpoint {
            let _ = std::fs::remove_file(&self.endpoint);
        }
    }
}

pub struct LocalStream(UnixStream);

impl LocalStream {
    pub fn set_io_timeout(&mut self, timeout: Duration) -> std::io::Result<()> {
        self.0.set_read_timeout(Some(timeout))?;
        self.0.set_write_timeout(Some(timeout))
    }
}

impl Read for LocalStream {
    fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
        self.0.read(buffer)
    }
}

impl Write for LocalStream {
    fn write(&mut self, buffer: &[u8]) -> std::io::Result<usize> {
        self.0.write(buffer)
    }

    fn flush(&mut self) -> std::io::Result<()> {
        self.0.flush()
    }
}

impl StoreLock {
    pub fn acquire(store: &Path) -> std::io::Result<Self> {
        let lock = OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .mode(0o600)
            .open(store.join("workspace-daemon.lock"))?;
        let result = unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) };
        if result != 0 {
            let error = Error::last_os_error();
            return Err(Error::new(
                ErrorKind::AddrInUse,
                format!("workspace daemon store is already owned: {error}"),
            ));
        }
        lock.set_len(0)?;
        write_lock_metadata(&lock)?;
        Ok(Self { _file: lock })
    }
}

fn write_lock_metadata(lock: &File) -> std::io::Result<()> {
    let started_at = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    writeln!(
        &lock,
        "pid={} started_unix_ms={started_at}",
        std::process::id()
    )?;
    lock.sync_data()?;
    Ok(())
}

fn prepare_endpoint(endpoint: &Path) -> std::io::Result<()> {
    let metadata = match std::fs::symlink_metadata(endpoint) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == ErrorKind::NotFound => return Ok(()),
        Err(error) => return Err(error),
    };
    if !metadata.file_type().is_socket() {
        return Err(Error::new(
            ErrorKind::AlreadyExists,
            format!(
                "workspace daemon endpoint is not a socket: {}",
                endpoint.display()
            ),
        ));
    }
    match UnixStream::connect(endpoint) {
        Ok(_) => Err(Error::new(
            ErrorKind::AddrInUse,
            "workspace daemon endpoint is already accepting connections",
        )),
        Err(error)
            if matches!(
                error.kind(),
                ErrorKind::ConnectionRefused | ErrorKind::NotFound
            ) =>
        {
            std::fs::remove_file(endpoint)
        }
        Err(error) => Err(error),
    }
}
