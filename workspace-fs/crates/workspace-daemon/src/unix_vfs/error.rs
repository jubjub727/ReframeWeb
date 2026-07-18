use anyhow::Error;
use fuser::Errno;

pub fn errno(operation: &str, error: &Error) -> Errno {
    eprintln!("workspace-fs FUSE {operation} failed: {error:#}");
    error
        .downcast_ref::<std::io::Error>()
        .map(io_errno)
        .unwrap_or(Errno::EIO)
}

pub(super) fn io_errno(error: &std::io::Error) -> Errno {
    if let Some(code) = error.raw_os_error() {
        return Errno::from_i32(code);
    }
    match error.kind() {
        std::io::ErrorKind::NotFound => Errno::ENOENT,
        std::io::ErrorKind::PermissionDenied => Errno::EACCES,
        std::io::ErrorKind::AlreadyExists => Errno::EEXIST,
        std::io::ErrorKind::InvalidInput | std::io::ErrorKind::InvalidData => Errno::EINVAL,
        std::io::ErrorKind::NotADirectory => Errno::ENOTDIR,
        std::io::ErrorKind::IsADirectory => Errno::EISDIR,
        std::io::ErrorKind::DirectoryNotEmpty => Errno::ENOTEMPTY,
        std::io::ErrorKind::OutOfMemory => Errno::ENOMEM,
        std::io::ErrorKind::Unsupported => Errno::ENOTSUP,
        _ => Errno::EIO,
    }
}
