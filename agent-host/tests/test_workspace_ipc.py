from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from reframe_agent_host.workspace.protocol import (
    IdempotencyScope,
    OPERATION_METADATA,
    WorkspaceOperation,
)
from reframe_agent_host.workspace.errors import (
    WorkspaceOutcomeUnknownError,
    WorkspaceTransportError,
)
from reframe_agent_host.workspace.models import MountedWorkspace
from reframe_agent_host.workspace.service import WorkspaceDaemon, _read_frame, _write_frame
from reframe_agent_host.workspace.transport import LocalConnection, encode_frame


class _ShortWriteBuffer(BytesIO):
    def write(self, value) -> int:
        return super().write(value[:3])


class _DuplexStream:
    def __init__(self, incoming: bytes) -> None:
        self.incoming = BytesIO(incoming)
        self.written = bytearray()

    def read(self, size: int = -1) -> bytes:
        return self.incoming.read(size)

    def write(self, value) -> int:
        count = min(5, len(value))
        self.written.extend(value[:count])
        return count

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class WorkspaceIpcTests(unittest.TestCase):
    def test_mounted_workspace_reports_the_provider_backend(self) -> None:
        mounted = MountedWorkspace.model_validate(
            {
                "session_id": "task",
                "mount_path": "R:/workspace",
                "backend": "winfsp",
                "resident_files": 3,
                "resident_bytes": 4_096,
            }
        )

        self.assertEqual(mounted.backend, "winfsp")

    def test_start_terminates_a_daemon_when_endpoint_startup_fails(self) -> None:
        process = mock.Mock()
        process.poll.return_value = None

        def terminate() -> None:
            process.poll.return_value = -15

        process.terminate.side_effect = terminate
        with TemporaryDirectory() as temporary:
            daemon = WorkspaceDaemon(Path(temporary))

            def fail_startup() -> None:
                daemon._launched_process = process  # noqa: SLF001
                raise WorkspaceTransportError("injected startup timeout")

            daemon._ensure_connection = fail_startup  # type: ignore[method-assign]
            with self.assertRaisesRegex(
                WorkspaceTransportError, "injected startup timeout"
            ):
                daemon.start()

        process.terminate.assert_called_once()
        self.assertIsNone(daemon._launched_process)  # noqa: SLF001

    def test_failed_connection_retry_cleans_up_before_a_relaunch(self) -> None:
        process = mock.Mock()
        process.poll.return_value = None

        def terminate() -> None:
            process.poll.return_value = -15

        process.terminate.side_effect = terminate
        with TemporaryDirectory() as temporary:
            daemon = WorkspaceDaemon(Path(temporary))
            daemon._connect = mock.Mock(side_effect=OSError("not ready"))  # type: ignore[method-assign]
            daemon._connect_with_retry = mock.Mock(  # type: ignore[method-assign]
                side_effect=WorkspaceTransportError("injected retry timeout")
            )
            with mock.patch(
                "reframe_agent_host.workspace.service.launch_service",
                return_value=(process, Path(temporary) / "daemon.log"),
            ):
                with self.assertRaisesRegex(
                    WorkspaceTransportError, "injected retry timeout"
                ):
                    daemon._ensure_connection()  # noqa: SLF001

        process.terminate.assert_called_once()
        self.assertIsNone(daemon._launched_process)  # noqa: SLF001

    def test_frame_writer_handles_short_writes(self) -> None:
        stream = _ShortWriteBuffer()
        payload = {"request_id": "short", "operation": "health"}

        _write_frame(stream, payload)
        stream.seek(0)

        self.assertEqual(_read_frame(stream), payload)

    def test_durable_retry_reuses_the_exact_mutating_request(self) -> None:
        response = encode_frame(
            {
                "request_id": "host-1",
                "ok": True,
                "result": {"session_id": "task", "state": "closed"},
            }
        )
        first = _DuplexStream(b"")
        second = _DuplexStream(response)
        streams = iter((first, second))

        with TemporaryDirectory() as temporary:
            daemon = WorkspaceDaemon(Path(temporary))

            def connect() -> None:
                daemon._connection = LocalConnection(stream=next(streams))  # noqa: SLF001

            daemon._ensure_connection = connect  # type: ignore[method-assign]
            result = daemon.close_workspace("task")

        self.assertEqual(result.session_id, "task")
        self.assertEqual(first.written, second.written)
        request = _read_frame(BytesIO(first.written))
        self.assertEqual(request["operation"], "close_workspace")
        self.assertTrue(request["idempotency_key"].startswith("close_workspace-"))

    def test_process_local_transport_failure_is_not_replayed(self) -> None:
        stream = _DuplexStream(b"")
        connects = 0

        with TemporaryDirectory() as temporary:
            daemon = WorkspaceDaemon(Path(temporary))

            def connect() -> None:
                nonlocal connects
                connects += 1
                daemon._connection = LocalConnection(stream=stream)  # noqa: SLF001

            daemon._ensure_connection = connect  # type: ignore[method-assign]
            with self.assertRaisesRegex(
                WorkspaceOutcomeUnknownError,
                "outcome is unknown.*was not retried",
            ):
                daemon.shutdown()

        self.assertEqual(connects, 1)
        written = BytesIO(stream.written)
        request = _read_frame(written)
        self.assertEqual(request["operation"], "shutdown")
        self.assertEqual(written.read(), b"")

    def test_operation_metadata_covers_every_typed_operation(self) -> None:
        self.assertEqual(set(OPERATION_METADATA), set(WorkspaceOperation))
        process_local = {
            WorkspaceOperation.MOUNT_WORKSPACE,
            WorkspaceOperation.PREFETCH,
            WorkspaceOperation.UNMOUNT_WORKSPACE,
            WorkspaceOperation.SHUTDOWN,
        }
        self.assertEqual(
            {
                operation
                for operation, metadata in OPERATION_METADATA.items()
                if metadata.idempotency_scope is IdempotencyScope.PROCESS_LOCAL
            },
            process_local,
        )
        for metadata in OPERATION_METADATA.values():
            self.assertEqual(
                metadata.mutates,
                metadata.idempotency_scope is not IdempotencyScope.NONE,
            )

    @unittest.skipUnless(os.name == "nt", "Windows named-pipe behavior")
    def test_windows_pipe_cancels_a_stalled_read(self) -> None:
        from reframe_agent_host.workspace import windows_pipe

        kernel = mock.Mock()
        kernel.CreateEventW.return_value = 456
        kernel.ReadFile.return_value = False
        kernel.GetOverlappedResultEx.return_value = False
        kernel.GetOverlappedResult.return_value = False
        with (
            mock.patch.object(windows_pipe, "_KERNEL32", kernel),
            mock.patch.object(
                windows_pipe.ctypes,
                "get_last_error",
                side_effect=[997, 258],
            ),
        ):
            pipe = windows_pipe.WindowsPipe(123, timeout_seconds=0.001)
            with self.assertRaises(TimeoutError):
                pipe.read(1)
            pipe._handle = None  # noqa: SLF001

        kernel.CancelIoEx.assert_called_once()


if __name__ == "__main__":
    unittest.main()
