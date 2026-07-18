use std::ffi::CString;
use std::io;
use std::os::unix::ffi::OsStrExt;
use std::path::Path;

pub(super) fn unmount_path(path: &Path) -> io::Result<()> {
    let native = CString::new(path.as_os_str().as_bytes())
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidInput, error))?;
    #[cfg(target_os = "linux")]
    let result = unsafe { libc::umount2(native.as_ptr(), 0) };
    #[cfg(not(target_os = "linux"))]
    let result = unsafe { libc::unmount(native.as_ptr(), 0) };
    if result == 0 {
        return Ok(());
    }
    let error = io::Error::last_os_error();
    #[cfg(target_os = "linux")]
    if error.raw_os_error() == Some(libc::EPERM) {
        return unmount_with_helper(path);
    }
    Err(error)
}

pub(super) fn is_already_unmounted(error: &io::Error) -> bool {
    matches!(
        error.raw_os_error(),
        Some(libc::EINVAL) | Some(libc::ENOENT)
    )
}

#[cfg(target_os = "linux")]
fn unmount_with_helper(path: &Path) -> io::Result<()> {
    let mut last_error = None;
    for helper in ["fusermount3", "fusermount"] {
        match std::process::Command::new(helper)
            .arg("-u")
            .arg(path)
            .status()
        {
            Ok(status) if status.success() => return Ok(()),
            Ok(status) => {
                last_error = Some(io::Error::other(format!(
                    "{helper} exited with status {status}"
                )));
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                last_error = Some(error);
            }
            Err(error) => return Err(error),
        }
    }
    Err(last_error.unwrap_or_else(|| io::Error::other("no FUSE unmount helper is available")))
}
