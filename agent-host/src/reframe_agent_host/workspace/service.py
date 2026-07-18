from __future__ import annotations

import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any, BinaryIO
from uuid import uuid4
import warnings

from pydantic import ValidationError

from reframe_agent_host.workspace.client_operations import TypedWorkspaceOperations
from reframe_agent_host.workspace.daemon_process import (
    launch_service,
    startup_diagnostics,
)
from reframe_agent_host.workspace.errors import (
    WorkspaceError,
    WorkspaceOutcomeUnknownError,
    WorkspaceRemoteError,
    WorkspaceTransportError,
)
from reframe_agent_host.workspace.location import persistent_store
from reframe_agent_host.workspace.protocol import (
    IdempotencyScope,
    WorkspaceOperation,
    WorkspaceResponse,
    operation_metadata,
    request_payload,
)
from reframe_agent_host.workspace.transport import (
    LocalConnection,
    connect_local,
    daemon_endpoint,
    encode_frame,
    read_frame as _transport_read_frame,
    write_encoded_frame,
    write_frame as _transport_write_frame,
)


_STARTUP_TIMEOUT_SECONDS = 10.0
_REQUEST_ATTEMPTS = 2


class WorkspaceDaemon(TypedWorkspaceOperations):
    """Connection lifecycle and retry policy for the typed workspace client."""

    def __init__(self, store: Path | None = None) -> None:
        self.store = (store or default_store()).resolve()
        self._connection: LocalConnection | None = None
        self._request_number = 0
        self._request_lock = threading.RLock()
        self._launched_process: subprocess.Popen[bytes] | None = None
        self._diagnostic_log: Path | None = None

    def __enter__(self) -> "WorkspaceDaemon":
        self.start()
        return self

    def __exit__(self, _kind, _error, _traceback) -> None:
        self.close()

    def start(self) -> None:
        try:
            with self._request_lock:
                if self._connection is not None:
                    return
                self._ensure_connection()
            self.hello()
        except Exception:
            self.close()
            self._terminate_failed_launch()
            raise

    def close(self) -> None:
        with self._request_lock:
            self._close_connection()

    def request(self, operation: str, **arguments: Any) -> Any:
        """Compatibility shim for callers migrating to the typed methods."""
        warnings.warn(
            "WorkspaceDaemon.request() is deprecated; use a typed operation method",
            DeprecationWarning,
            stacklevel=2,
        )
        try:
            typed_operation = WorkspaceOperation(operation)
        except ValueError as error:
            raise WorkspaceError(f"unsupported workspace operation: {operation}") from error
        return self._request(typed_operation, **arguments)

    def _request(self, operation: WorkspaceOperation, **arguments: Any) -> Any:
        with self._request_lock:
            self._request_number += 1
            request_id = f"host-{self._request_number}"
            metadata = operation_metadata(operation)
            idempotency_key = (
                f"{operation.value}-{uuid4()}" if metadata.mutates else None
            )
            payload = request_payload(
                operation,
                request_id,
                idempotency_key=idempotency_key,
                arguments=arguments,
            )
            frame = encode_frame(payload)
            last_error: WorkspaceTransportError | None = None
            attempts = (
                1
                if metadata.idempotency_scope is IdempotencyScope.PROCESS_LOCAL
                else _REQUEST_ATTEMPTS
            )
            for _attempt in range(attempts):
                try:
                    if self._connection is None:
                        self._ensure_connection()
                    stream = self._require_connection().stream
                    write_encoded_frame(stream, frame)
                    response = WorkspaceResponse.model_validate(
                        _transport_read_frame(stream)
                    )
                    if response.request_id != request_id:
                        raise WorkspaceError(
                            "workspace response request id did not match"
                        )
                    if not response.ok:
                        assert response.error is not None
                        raise WorkspaceRemoteError(response.error)
                    return response.result
                except WorkspaceTransportError as error:
                    last_error = error
                except OSError as error:
                    last_error = WorkspaceTransportError(
                        "workspace daemon transport failed"
                    )
                    last_error.__cause__ = error
                except ValidationError as error:
                    raise WorkspaceError(
                        f"workspace {operation.value} returned an invalid response envelope"
                    ) from error
                finally:
                    self._close_connection()
            assert last_error is not None
            diagnostics = startup_diagnostics(self._diagnostic_log)
            if metadata.idempotency_scope is IdempotencyScope.PROCESS_LOCAL:
                detail = (
                    f"workspace {operation.value} transport failed; its outcome is "
                    "unknown and the process-local mutation was not retried because "
                    "the daemon may have restarted"
                )
                if diagnostics:
                    detail += f"; recent daemon output:\n{diagnostics}"
                raise WorkspaceOutcomeUnknownError(detail) from last_error
            if diagnostics:
                raise WorkspaceTransportError(
                    f"{last_error}; recent daemon output:\n{diagnostics}"
                ) from last_error
            raise last_error

    def _after_shutdown(self) -> None:
        if self._launched_process is None:
            return
        try:
            self._launched_process.wait(timeout=5)
        except subprocess.TimeoutExpired as error:
            raise WorkspaceError(
                "workspace daemon accepted shutdown but did not exit"
            ) from error

    def _require_connection(self) -> LocalConnection:
        if self._connection is None:
            raise WorkspaceTransportError("workspace backing service is not running")
        return self._connection

    def _connect(self) -> None:
        self._connection = connect_local(self.store)

    def _ensure_connection(self) -> None:
        self.store.mkdir(parents=True, exist_ok=True)
        try:
            self._connect()
        except OSError:
            process = self._launched_process
            if process is None or process.poll() is not None:
                self._launched_process = None
                self._launch_service()
            try:
                self._connect_with_retry()
            except Exception:
                self._terminate_failed_launch()
                raise

    def _connect_with_retry(self) -> None:
        deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
        error: OSError | None = None
        while time.monotonic() < deadline:
            try:
                self._connect()
                return
            except OSError as caught:
                error = caught
                time.sleep(0.05)
        status = (
            self._launched_process.poll()
            if self._launched_process is not None
            else None
        )
        detail = "workspace backing service did not open its local endpoint"
        if status is not None:
            detail += f" (daemon exited with status {status})"
        diagnostics = startup_diagnostics(self._diagnostic_log)
        if diagnostics:
            detail += f"; recent daemon output:\n{diagnostics}"
        raise WorkspaceTransportError(detail) from error

    def _launch_service(self) -> None:
        if (
            self._launched_process is not None
            and self._launched_process.poll() is None
        ):
            raise WorkspaceTransportError(
                "workspace backing service is already starting"
            )
        self._launched_process, self._diagnostic_log = launch_service(self.store)

    def _terminate_failed_launch(self) -> None:
        process = self._launched_process
        if process is None:
            return
        if process.poll() is not None:
            self._launched_process = None
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
        except OSError:
            pass
        if process.poll() is not None:
            self._launched_process = None

    def _close_connection(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None


def default_store() -> Path:
    configured = os.getenv("REFRAME_WORKSPACE_STORE")
    return Path(configured) if configured else persistent_store()


# Kept import-compatible while callers move framing tests to the transport module.
def _write_frame(stream: BinaryIO, payload: dict[str, Any]) -> None:
    _transport_write_frame(stream, payload)


def _read_frame(stream: BinaryIO) -> dict[str, Any]:
    return _transport_read_frame(stream)
