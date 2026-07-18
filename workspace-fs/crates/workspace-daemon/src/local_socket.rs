#[cfg(unix)]
mod platform {
    use std::io::{Read, Write};
    use std::os::unix::fs::PermissionsExt;
    use std::os::unix::net::{UnixListener, UnixStream};
    use std::path::Path;

    pub struct LocalListener(UnixListener);

    impl LocalListener {
        pub fn bind(store: &Path) -> std::io::Result<Self> {
            let endpoint = store.join("workspace-daemon.sock");
            if endpoint.exists() {
                std::fs::remove_file(&endpoint)?;
            }
            let listener = UnixListener::bind(&endpoint)?;
            std::fs::set_permissions(endpoint, std::fs::Permissions::from_mode(0o600))?;
            Ok(Self(listener))
        }

        pub fn accept(&self) -> std::io::Result<LocalStream> {
            self.0.accept().map(|(stream, _)| LocalStream(stream))
        }
    }

    pub struct LocalStream(UnixStream);

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
}

#[cfg(windows)]
mod platform {
    use std::io::{Read, Write};
    use std::path::Path;

    use windows::Win32::Foundation::{
        CloseHandle, ERROR_BROKEN_PIPE, ERROR_PIPE_CONNECTED, HANDLE,
    };
    use windows::Win32::Storage::FileSystem::{
        FlushFileBuffers, PIPE_ACCESS_DUPLEX, ReadFile, WriteFile,
    };
    use windows::Win32::System::Pipes::{
        ConnectNamedPipe, CreateNamedPipeW, DisconnectNamedPipe, PIPE_READMODE_BYTE,
        PIPE_REJECT_REMOTE_CLIENTS, PIPE_TYPE_BYTE, PIPE_UNLIMITED_INSTANCES, PIPE_WAIT,
    };
    use windows::core::{HRESULT, PCWSTR};

    pub struct LocalListener {
        name: Vec<u16>,
    }

    impl LocalListener {
        pub fn bind(store: &Path) -> std::io::Result<Self> {
            let name = pipe_name(store)
                .encode_utf16()
                .chain([0])
                .collect::<Vec<_>>();
            Ok(Self { name })
        }

        pub fn accept(&self) -> std::io::Result<LocalStream> {
            let handle = unsafe {
                CreateNamedPipeW(
                    PCWSTR::from_raw(self.name.as_ptr()),
                    PIPE_ACCESS_DUPLEX,
                    PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
                    PIPE_UNLIMITED_INSTANCES,
                    1024 * 1024,
                    1024 * 1024,
                    0,
                    None,
                )
            };
            if handle.is_invalid() {
                return Err(io_error(windows::core::Error::from_win32()));
            }
            match unsafe { ConnectNamedPipe(handle, None) } {
                Ok(()) => Ok(LocalStream(handle)),
                Err(error) if error.code() == HRESULT::from_win32(ERROR_PIPE_CONNECTED.0) => {
                    Ok(LocalStream(handle))
                }
                Err(error) => {
                    unsafe { CloseHandle(handle) }.ok();
                    Err(io_error(error))
                }
            }
        }
    }

    pub struct LocalStream(HANDLE);

    impl Read for LocalStream {
        fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
            let mut read = 0;
            match unsafe { ReadFile(self.0, Some(buffer), Some(&mut read), None) } {
                Ok(()) => Ok(read as usize),
                Err(error) if error.code() == HRESULT::from_win32(ERROR_BROKEN_PIPE.0) => Ok(0),
                Err(error) => Err(io_error(error)),
            }
        }
    }

    impl Write for LocalStream {
        fn write(&mut self, buffer: &[u8]) -> std::io::Result<usize> {
            let mut written = 0;
            unsafe { WriteFile(self.0, Some(buffer), Some(&mut written), None) }
                .map_err(io_error)?;
            Ok(written as usize)
        }

        fn flush(&mut self) -> std::io::Result<()> {
            unsafe { FlushFileBuffers(self.0) }.map_err(io_error)
        }
    }

    impl Drop for LocalStream {
        fn drop(&mut self) {
            unsafe {
                DisconnectNamedPipe(self.0).ok();
                CloseHandle(self.0).ok();
            }
        }
    }

    fn pipe_name(store: &Path) -> String {
        let normalized = store.to_string_lossy().replace('/', "\\").to_lowercase();
        let mut hash = 0xcbf29ce484222325u64;
        for byte in normalized.as_bytes() {
            hash ^= u64::from(*byte);
            hash = hash.wrapping_mul(0x100000001b3);
        }
        format!(r"\\.\pipe\reframe-workspace-{hash:016x}")
    }

    fn io_error(error: windows::core::Error) -> std::io::Error {
        std::io::Error::from_raw_os_error(error.code().0)
    }
}

pub use platform::{LocalListener, LocalStream};
