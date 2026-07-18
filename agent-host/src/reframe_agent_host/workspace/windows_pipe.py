from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading


_ERROR_BROKEN_PIPE = 109
_ERROR_IO_PENDING = 997
_WAIT_TIMEOUT = 258
_FILE_FLAG_OVERLAPPED = 0x40000000
_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_OPEN_EXISTING = 3


class _Overlapped(ctypes.Structure):
    _fields_ = (
        ("Internal", ctypes.c_size_t),
        ("InternalHigh", ctypes.c_size_t),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    )


class WindowsPipe:
    def __init__(self, handle: int, timeout_seconds: float) -> None:
        self._handle = handle
        self._timeout_ms = max(1, int(timeout_seconds * 1000))
        self._lock = threading.Lock()

    @property
    def closed(self) -> bool:
        return self._handle is None

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise ValueError("WindowsPipe.read requires a bounded size")
        if size == 0:
            return b""
        with self._lock:
            handle = self._require_handle()
            buffer = ctypes.create_string_buffer(size)
            transferred = self._run_io(
                handle,
                lambda pending: _KERNEL32.ReadFile(
                    handle,
                    buffer,
                    size,
                    None,
                    ctypes.byref(pending),
                ),
                "read",
            )
            return buffer.raw[:transferred]

    def write(self, value) -> int:
        encoded = bytes(value)
        if not encoded:
            return 0
        with self._lock:
            handle = self._require_handle()
            buffer = ctypes.create_string_buffer(encoded)
            return self._run_io(
                handle,
                lambda pending: _KERNEL32.WriteFile(
                    handle,
                    buffer,
                    len(encoded),
                    None,
                    ctypes.byref(pending),
                ),
                "write",
            )

    def flush(self) -> None:
        self._require_handle()

    def close(self) -> None:
        with self._lock:
            if self._handle is not None:
                _KERNEL32.CancelIoEx(self._handle, None)
                _KERNEL32.CloseHandle(self._handle)
                self._handle = None

    def _run_io(self, handle: int, start, description: str) -> int:
        event = _KERNEL32.CreateEventW(None, True, False, None)
        if not event:
            raise ctypes.WinError(ctypes.get_last_error())
        pending = _Overlapped()
        pending.hEvent = event
        try:
            if not start(pending):
                error = ctypes.get_last_error()
                if error == _ERROR_BROKEN_PIPE and description == "read":
                    return 0
                if error != _ERROR_IO_PENDING:
                    raise ctypes.WinError(error)
            transferred = wintypes.DWORD()
            if _KERNEL32.GetOverlappedResultEx(
                handle,
                ctypes.byref(pending),
                ctypes.byref(transferred),
                self._timeout_ms,
                False,
            ):
                return transferred.value
            error = ctypes.get_last_error()
            if error == _ERROR_BROKEN_PIPE and description == "read":
                return 0
            if error != _WAIT_TIMEOUT:
                raise ctypes.WinError(error)
            _KERNEL32.CancelIoEx(handle, ctypes.byref(pending))
            _KERNEL32.GetOverlappedResult(
                handle,
                ctypes.byref(pending),
                ctypes.byref(transferred),
                True,
            )
            raise TimeoutError(f"workspace named-pipe {description} timed out")
        finally:
            _KERNEL32.CloseHandle(event)

    def _require_handle(self) -> int:
        if self._handle is None:
            raise OSError("workspace named pipe is closed")
        return self._handle


def open_windows_pipe(name: str, timeout_seconds: float) -> WindowsPipe:
    handle = _KERNEL32.CreateFileW(
        name,
        _GENERIC_READ | _GENERIC_WRITE,
        0,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_OVERLAPPED,
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    return WindowsPipe(handle, timeout_seconds)


_KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
_KERNEL32.CreateFileW.argtypes = (
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
)
_KERNEL32.CreateFileW.restype = wintypes.HANDLE
_KERNEL32.CreateEventW.argtypes = (
    wintypes.LPVOID,
    wintypes.BOOL,
    wintypes.BOOL,
    wintypes.LPCWSTR,
)
_KERNEL32.CreateEventW.restype = wintypes.HANDLE
_KERNEL32.ReadFile.argtypes = (
    wintypes.HANDLE,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.LPVOID,
    ctypes.POINTER(_Overlapped),
)
_KERNEL32.ReadFile.restype = wintypes.BOOL
_KERNEL32.WriteFile.argtypes = _KERNEL32.ReadFile.argtypes
_KERNEL32.WriteFile.restype = wintypes.BOOL
_KERNEL32.GetOverlappedResultEx.argtypes = (
    wintypes.HANDLE,
    ctypes.POINTER(_Overlapped),
    ctypes.POINTER(wintypes.DWORD),
    wintypes.DWORD,
    wintypes.BOOL,
)
_KERNEL32.GetOverlappedResultEx.restype = wintypes.BOOL
_KERNEL32.GetOverlappedResult.argtypes = (
    wintypes.HANDLE,
    ctypes.POINTER(_Overlapped),
    ctypes.POINTER(wintypes.DWORD),
    wintypes.BOOL,
)
_KERNEL32.GetOverlappedResult.restype = wintypes.BOOL
_KERNEL32.CancelIoEx.argtypes = (wintypes.HANDLE, wintypes.LPVOID)
_KERNEL32.CancelIoEx.restype = wintypes.BOOL
_KERNEL32.CloseHandle.argtypes = (wintypes.HANDLE,)
_KERNEL32.CloseHandle.restype = wintypes.BOOL
