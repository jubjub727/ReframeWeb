from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import socket
import struct
from typing import Any, BinaryIO

from reframe_agent_host.workspace.errors import (
    WorkspaceError,
    WorkspaceTransportError,
)
from reframe_agent_host.workspace.protocol import MAX_FRAME_BYTES


CONNECT_TIMEOUT_SECONDS = 2.0
IO_TIMEOUT_SECONDS = 10.0


@dataclass(slots=True)
class LocalConnection:
    stream: BinaryIO
    socket: socket.socket | None = None

    def close(self) -> None:
        try:
            self.stream.close()
        finally:
            if self.socket is not None:
                self.socket.close()


def connect_local(store: Path) -> LocalConnection:
    endpoint = daemon_endpoint(store)
    if os.name == "nt":
        from reframe_agent_host.workspace.windows_pipe import open_windows_pipe

        return LocalConnection(stream=open_windows_pipe(endpoint, IO_TIMEOUT_SECONDS))
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(CONNECT_TIMEOUT_SECONDS)
    try:
        client.connect(endpoint)
        client.settimeout(IO_TIMEOUT_SECONDS)
        return LocalConnection(
            stream=client.makefile("rwb", buffering=0),
            socket=client,
        )
    except Exception:
        client.close()
        raise


def daemon_endpoint(store: Path) -> str:
    if os.name != "nt":
        return str(store / "workspace-daemon.sock")
    normalized = str(store).replace("/", "\\").lower().encode()
    value = 0xCBF29CE484222325
    for byte in normalized:
        value ^= byte
        value = (value * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return rf"\\.\pipe\reframe-workspace-{value:016x}"


def encode_frame(payload: dict[str, Any]) -> bytes:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_FRAME_BYTES:
        raise WorkspaceError("workspace request exceeds the protocol frame limit")
    return struct.pack("<I", len(encoded)) + encoded


def write_encoded_frame(stream: BinaryIO, frame: bytes) -> None:
    remaining = memoryview(frame)
    while remaining:
        try:
            written = stream.write(remaining)
        except OSError as error:
            raise WorkspaceTransportError("failed to write workspace request") from error
        if written is None or written <= 0:
            raise WorkspaceTransportError("workspace protocol stream stopped accepting data")
        remaining = remaining[written:]
    try:
        stream.flush()
    except OSError as error:
        raise WorkspaceTransportError("failed to flush workspace request") from error


def write_frame(stream: BinaryIO, payload: dict[str, Any]) -> None:
    write_encoded_frame(stream, encode_frame(payload))


def read_frame(stream: BinaryIO) -> dict[str, Any]:
    try:
        length = struct.unpack("<I", read_exact(stream, 4))[0]
    except struct.error as error:
        raise WorkspaceTransportError("workspace response has an invalid frame header") from error
    if length > MAX_FRAME_BYTES:
        raise WorkspaceError("workspace response exceeds the protocol frame limit")
    encoded = read_exact(stream, length)
    try:
        value = json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkspaceError("workspace response is not valid JSON") from error
    if not isinstance(value, dict):
        raise WorkspaceError("workspace response must be a JSON object")
    return value


def read_exact(stream: BinaryIO, length: int) -> bytes:
    value = bytearray()
    while len(value) < length:
        try:
            chunk = stream.read(length - len(value))
        except OSError as error:
            raise WorkspaceTransportError(
                f"failed to read workspace response ({len(value)} of {length} bytes)"
            ) from error
        if not chunk:
            raise WorkspaceTransportError(
                "workspace backing service closed its protocol stream"
            )
        value.extend(chunk)
    return bytes(value)

