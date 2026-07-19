use std::io::{self, ErrorKind};
use std::os::unix::fs::{FileTypeExt as _, MetadataExt as _};
use std::path::{Path, PathBuf};

#[derive(Debug)]
pub(super) struct SocketGuard {
    pub(super) path: PathBuf,
    device: u64,
    inode: u64,
}

impl SocketGuard {
    pub(super) fn new(path: &Path) -> io::Result<Self> {
        let metadata = std::fs::symlink_metadata(path)?;
        if !metadata.file_type().is_socket() {
            return Err(io::Error::new(
                ErrorKind::InvalidData,
                format!("bound endpoint is not a Unix socket: {}", path.display()),
            ));
        }
        Ok(Self {
            path: path.to_owned(),
            device: metadata.dev(),
            inode: metadata.ino(),
        })
    }

    fn still_owns_endpoint(&self) -> bool {
        std::fs::symlink_metadata(&self.path).is_ok_and(|metadata| {
            metadata.file_type().is_socket()
                && metadata.dev() == self.device
                && metadata.ino() == self.inode
        })
    }
}

impl Drop for SocketGuard {
    fn drop(&mut self) {
        if self.still_owns_endpoint() {
            let _ = std::fs::remove_file(&self.path);
        }
    }
}

pub(super) fn prepare_endpoint(path: &Path) -> io::Result<()> {
    let original = match std::fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == ErrorKind::NotFound => return Ok(()),
        Err(error) => return Err(error),
    };
    if !original.file_type().is_socket() {
        return Err(io::Error::new(
            ErrorKind::AlreadyExists,
            format!("local endpoint is not a Unix socket: {}", path.display()),
        ));
    }

    match std::os::unix::net::UnixStream::connect(path) {
        Ok(_stream) => Err(io::Error::new(
            ErrorKind::AddrInUse,
            format!(
                "local endpoint is already accepting connections: {}",
                path.display()
            ),
        )),
        Err(error)
            if matches!(
                error.kind(),
                ErrorKind::ConnectionRefused | ErrorKind::NotFound
            ) =>
        {
            remove_if_same_socket(path, &original)
        }
        Err(error) => Err(error),
    }
}

fn remove_if_same_socket(path: &Path, original: &std::fs::Metadata) -> io::Result<()> {
    let current = std::fs::symlink_metadata(path)?;
    if current.file_type().is_socket()
        && current.dev() == original.dev()
        && current.ino() == original.ino()
    {
        return std::fs::remove_file(path);
    }
    Err(io::Error::new(
        ErrorKind::AlreadyExists,
        format!(
            "local endpoint changed while checking it: {}",
            path.display()
        ),
    ))
}
