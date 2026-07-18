use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::os::windows::fs::OpenOptionsExt;
use std::path::Path;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use windows::Win32::Foundation::{
    CloseHandle, ERROR_BROKEN_PIPE, ERROR_IO_PENDING, ERROR_PIPE_CONNECTED, HANDLE, WAIT_TIMEOUT,
};
use windows::Win32::Storage::FileSystem::{
    FILE_FLAG_OVERLAPPED, PIPE_ACCESS_DUPLEX, ReadFile, WriteFile,
};
use windows::Win32::System::IO::{
    CancelIoEx, GetOverlappedResult, GetOverlappedResultEx, OVERLAPPED,
};
use windows::Win32::System::Pipes::{
    ConnectNamedPipe, CreateNamedPipeW, PIPE_READMODE_BYTE, PIPE_REJECT_REMOTE_CLIENTS,
    PIPE_TYPE_BYTE, PIPE_UNLIMITED_INSTANCES, PIPE_WAIT,
};
use windows::Win32::System::Threading::CreateEventW;
use windows::core::{HRESULT, PCWSTR};

pub struct LocalListener {
    name: Vec<u16>,
    _lock: StoreLock,
}

pub struct StoreLock {
    _file: File,
}

impl LocalListener {
    pub fn bind(store: &Path) -> std::io::Result<Self> {
        let lock = StoreLock::acquire(store)?;
        let name = pipe_name(store)
            .encode_utf16()
            .chain([0])
            .collect::<Vec<_>>();
        Ok(Self { name, _lock: lock })
    }

    pub fn accept(&self) -> std::io::Result<LocalStream> {
        let handle = unsafe {
            CreateNamedPipeW(
                PCWSTR::from_raw(self.name.as_ptr()),
                PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED,
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
        connect(handle)
            .map(|()| LocalStream::new(handle))
            .inspect_err(|_| {
                unsafe { CloseHandle(handle) }.ok();
            })
    }
}

pub struct LocalStream {
    handle: HANDLE,
    timeout: Duration,
}

impl LocalStream {
    fn new(handle: HANDLE) -> Self {
        Self {
            handle,
            timeout: Duration::from_secs(10),
        }
    }

    pub fn set_io_timeout(&mut self, timeout: Duration) -> std::io::Result<()> {
        if timeout.is_zero() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                "workspace daemon I/O timeout must be non-zero",
            ));
        }
        self.timeout = timeout;
        Ok(())
    }
}

impl Read for LocalStream {
    fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
        let mut pending = PendingIo::new()?;
        let started = unsafe {
            ReadFile(
                self.handle,
                Some(buffer),
                None,
                Some(&mut pending.overlapped),
            )
        };
        match complete_io(self.handle, &pending.overlapped, started, self.timeout) {
            Ok(read) => Ok(read as usize),
            Err(error) if error.code() == HRESULT::from_win32(ERROR_BROKEN_PIPE.0) => Ok(0),
            Err(error) => Err(io_error(error)),
        }
    }
}

impl Write for LocalStream {
    fn write(&mut self, buffer: &[u8]) -> std::io::Result<usize> {
        let mut pending = PendingIo::new()?;
        let started = unsafe {
            WriteFile(
                self.handle,
                Some(buffer),
                None,
                Some(&mut pending.overlapped),
            )
        };
        complete_io(self.handle, &pending.overlapped, started, self.timeout)
            .map(|written| written as usize)
            .map_err(io_error)
    }

    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

impl Drop for LocalStream {
    fn drop(&mut self) {
        // DisconnectNamedPipe would discard a response not yet read by the client.
        unsafe { CloseHandle(self.handle) }.ok();
    }
}

struct PendingIo {
    overlapped: OVERLAPPED,
    event: HANDLE,
}

impl PendingIo {
    fn new() -> std::io::Result<Self> {
        let event = unsafe { CreateEventW(None, true, false, PCWSTR::null()) }.map_err(io_error)?;
        let overlapped = OVERLAPPED {
            hEvent: event,
            ..OVERLAPPED::default()
        };
        Ok(Self { overlapped, event })
    }
}

impl Drop for PendingIo {
    fn drop(&mut self) {
        unsafe { CloseHandle(self.event) }.ok();
    }
}

fn connect(handle: HANDLE) -> std::io::Result<()> {
    let mut pending = PendingIo::new()?;
    match unsafe { ConnectNamedPipe(handle, Some(&mut pending.overlapped)) } {
        Ok(()) => Ok(()),
        Err(error) if error.code() == HRESULT::from_win32(ERROR_PIPE_CONNECTED.0) => Ok(()),
        Err(error) if error.code() == HRESULT::from_win32(ERROR_IO_PENDING.0) => {
            let mut transferred = 0;
            unsafe { GetOverlappedResult(handle, &pending.overlapped, &mut transferred, true) }
                .map_err(io_error)
        }
        Err(error) => Err(io_error(error)),
    }
}

fn complete_io(
    handle: HANDLE,
    overlapped: &OVERLAPPED,
    started: windows::core::Result<()>,
    timeout: Duration,
) -> windows::core::Result<u32> {
    if let Err(error) = started {
        if error.code() != HRESULT::from_win32(ERROR_IO_PENDING.0) {
            return Err(error);
        }
    }
    let milliseconds = u32::try_from(timeout.as_millis())
        .unwrap_or(u32::MAX)
        .max(1);
    let mut transferred = 0;
    match unsafe {
        GetOverlappedResultEx(handle, overlapped, &mut transferred, milliseconds, false)
    } {
        Ok(()) => Ok(transferred),
        Err(error) if error.code() == HRESULT::from_win32(WAIT_TIMEOUT.0) => {
            unsafe { CancelIoEx(handle, Some(overlapped)) }.ok();
            unsafe { GetOverlappedResult(handle, overlapped, &mut transferred, true) }.ok();
            Err(windows::core::Error::from_hresult(HRESULT::from_win32(
                WAIT_TIMEOUT.0,
            )))
        }
        Err(error) => Err(error),
    }
}

impl StoreLock {
    pub fn acquire(store: &Path) -> std::io::Result<Self> {
        let lock = OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .share_mode(0)
            .open(store.join("workspace-daemon.lock"))?;
        lock.set_len(0)?;
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
        Ok(Self { _file: lock })
    }
}

pub(super) fn pipe_name(store: &Path) -> String {
    let normalized = store.to_string_lossy().replace('/', "\\").to_lowercase();
    let mut hash = 0xcbf29ce484222325u64;
    for byte in normalized.as_bytes() {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!(r"\\.\pipe\reframe-workspace-{hash:016x}")
}

fn io_error(error: windows::core::Error) -> std::io::Error {
    if error.code() == HRESULT::from_win32(WAIT_TIMEOUT.0) {
        return std::io::Error::new(
            std::io::ErrorKind::TimedOut,
            "workspace daemon client I/O timed out",
        );
    }
    std::io::Error::from_raw_os_error(error.code().0)
}
