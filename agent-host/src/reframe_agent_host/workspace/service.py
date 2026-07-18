from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import time
from typing import Any, BinaryIO
from uuid import uuid4

from reframe_agent_host.workspace.protocol import (
    MAX_FRAME_BYTES,
    WorkspaceResponse,
    request_payload,
)
from reframe_agent_host.workspace.location import persistent_store


_MUTATING_OPERATIONS = {
    "create_workspace",
    "apply_policy",
    "mount_workspace",
    "prefetch",
    "commit_checkpoint",
    "unmount_workspace",
    "close_workspace",
    "destroy_ephemeral_workspace",
    "shutdown",
}


class WorkspaceError(RuntimeError):
    pass


class WorkspaceDaemon:
    def __init__(self, store: Path | None = None) -> None:
        self.store = (store or default_store()).resolve()
        self._socket: socket.socket | None = None
        self._stream: BinaryIO | None = None
        self._request_number = 0

    def __enter__(self) -> "WorkspaceDaemon":
        self.start()
        return self

    def __exit__(self, _kind, _error, _traceback) -> None:
        self.close()

    def start(self) -> None:
        if self._stream is not None:
            return
        self.store.mkdir(parents=True, exist_ok=True)
        try:
            self._connect()
        except OSError:
            self._launch_service()
            self._connect_with_retry()
        try:
            self.request("hello")
        except Exception:
            self.close()
            raise

    def request(self, operation: str, **arguments: Any) -> Any:
        if self._stream is None:
            self._connect_with_retry()
        try:
            stream = self._require_stream()
            self._request_number += 1
            request_id = f"host-{self._request_number}"
            idempotency_key = None
            if operation in _MUTATING_OPERATIONS:
                idempotency_key = f"{operation}-{uuid4()}"
            payload = request_payload(
                operation,
                request_id,
                idempotency_key=idempotency_key,
                arguments=arguments,
            )
            _write_frame(stream, payload)
            response = WorkspaceResponse.model_validate(_read_frame(stream))
            if response.request_id != request_id:
                raise WorkspaceError("workspace response request id did not match")
            if not response.ok:
                detail = response.error
                if detail is None:
                    raise WorkspaceError(f"workspace {operation} failed")
                raise WorkspaceError(f"{detail.code}: {detail.message}")
            return response.result
        finally:
            self.close()

    def close(self) -> None:
        try:
            if self._stream is not None:
                self._stream.close()
        finally:
            self._stream = None
            if self._socket is not None:
                self._socket.close()
            self._socket = None

    def _require_stream(self) -> BinaryIO:
        if self._stream is None:
            raise WorkspaceError("workspace backing service is not running")
        return self._stream

    def _connect(self) -> None:
        if os.name == "nt":
            self._stream = _open_windows_pipe(daemon_endpoint(self.store))
            return
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            client.connect(str(daemon_endpoint(self.store)))
        except Exception:
            client.close()
            raise
        self._socket = client
        self._stream = client.makefile("rwb", buffering=0)

    def _connect_with_retry(self) -> None:
        deadline = time.monotonic() + 10
        error: OSError | None = None
        while time.monotonic() < deadline:
            try:
                self._connect()
                return
            except OSError as caught:
                error = caught
                time.sleep(0.05)
        raise WorkspaceError("workspace backing service did not open its local socket") from error

    def _launch_service(self) -> None:
        command = backing_service_command(self.store)
        options: dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            options["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NO_WINDOW
            )
        else:
            options["start_new_session"] = True
        subprocess.Popen(command, **options)


def default_store() -> Path:
    configured = os.getenv("REFRAME_WORKSPACE_STORE")
    return Path(configured) if configured else persistent_store()


def backing_service_command(store: Path) -> list[str]:
    configured = os.getenv("REFRAME_WORKSPACE_DAEMON")
    if configured:
        executable = Path(configured).expanduser().resolve()
        if not executable.is_file():
            raise WorkspaceError(f"workspace backing service does not exist: {executable}")
        return [str(executable), "--store", str(store), "serve-socket"]

    binary = shutil.which("reframe-workspace-daemon")
    if binary is None:
        raise WorkspaceError(
            "workspace backing service is not installed; run 'uv sync' in agent-host"
        )
    return [binary, "--store", str(store), "serve-socket"]


def daemon_endpoint(store: Path) -> str:
    if os.name != "nt":
        return str(store / "workspace-daemon.sock")
    normalized = str(store).replace("/", "\\").lower().encode()
    value = 0xCBF29CE484222325
    for byte in normalized:
        value ^= byte
        value = (value * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return rf"\\.\pipe\reframe-workspace-{value:016x}"


def _open_windows_pipe(name: str) -> BinaryIO:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    create_file = ctypes.windll.kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        name,
        0x80000000 | 0x40000000,
        0,
        None,
        3,
        0,
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError()
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
    except Exception:
        ctypes.windll.kernel32.CloseHandle(handle)
        raise
    return os.fdopen(descriptor, "r+b", buffering=0)


def _write_frame(stream: BinaryIO, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_FRAME_BYTES:
        raise WorkspaceError("workspace request exceeds the protocol frame limit")
    stream.write(struct.pack("<I", len(encoded)))
    stream.write(encoded)
    stream.flush()


def _read_frame(stream: BinaryIO) -> dict[str, Any]:
    length = struct.unpack("<I", _read_exact(stream, 4))[0]
    if length > MAX_FRAME_BYTES:
        raise WorkspaceError("workspace response exceeds the protocol frame limit")
    return json.loads(_read_exact(stream, length))


def _read_exact(stream: BinaryIO, length: int) -> bytes:
    value = bytearray()
    while len(value) < length:
        chunk = stream.read(length - len(value))
        if not chunk:
            raise WorkspaceError("workspace backing service closed its protocol stream")
        value.extend(chunk)
    return bytes(value)
