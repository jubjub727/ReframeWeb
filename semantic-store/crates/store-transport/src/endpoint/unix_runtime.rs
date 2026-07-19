use std::io::{self, ErrorKind};
use std::os::unix::fs::{DirBuilderExt as _, MetadataExt as _, PermissionsExt as _};
use std::path::{Path, PathBuf};

use super::{PORTABLE_UNIX_SOCKET_PATH_CAPACITY, managed_socket_relative_path};

pub(super) fn default_endpoint_path(normalized_service_name: &str) -> PathBuf {
    let user_id = rustix::process::getuid().as_raw();
    let relative_path = managed_socket_relative_path(user_id, normalized_service_name);
    let base = std::env::var_os("XDG_RUNTIME_DIR")
        .map(PathBuf::from)
        .filter(|path| path.is_absolute() && path.is_dir())
        .unwrap_or_else(std::env::temp_dir);
    let preferred = base.join(&relative_path);
    if socket_path_fits(&preferred) {
        return preferred;
    }

    let fallback = Path::new("/tmp").join(relative_path);
    debug_assert!(socket_path_fits(&fallback));
    fallback
}

fn socket_path_fits(path: &Path) -> bool {
    use std::os::unix::ffi::OsStrExt as _;

    path.as_os_str().as_bytes().len() <= PORTABLE_UNIX_SOCKET_PATH_CAPACITY
}

pub(super) fn ensure_private_directory(path: &Path) -> io::Result<()> {
    let mut created = false;
    let mut builder = std::fs::DirBuilder::new();
    builder.mode(0o700);
    match builder.create(path) {
        Ok(()) => created = true,
        Err(error) if error.kind() == ErrorKind::AlreadyExists => {}
        Err(error) => return Err(error),
    }
    if created {
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o700))?;
    }

    let metadata = std::fs::symlink_metadata(path)?;
    let expected_uid = rustix::process::getuid().as_raw();
    if metadata.file_type().is_dir()
        && metadata.uid() == expected_uid
        && metadata.permissions().mode() & 0o777 == 0o700
    {
        return Ok(());
    }
    Err(io::Error::new(
        ErrorKind::PermissionDenied,
        format!(
            "Semantic Store runtime directory must be owned by uid {expected_uid} with mode 0700: {}",
            path.display()
        ),
    ))
}
