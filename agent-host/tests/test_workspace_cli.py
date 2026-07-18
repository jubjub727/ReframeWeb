from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from reframe_agent_host.commands.parser import build_parser
from reframe_agent_host.commands.workspace import (
    _checkpoint_memory_id,
    _latest_summary,
    _resolve_memory_sources,
)
from reframe_agent_host.workspace import WorkspaceError
from reframe_agent_host.workspace.service import (
    _read_frame,
    _write_frame,
    backing_service_command,
)
from reframe_agent_host.workspace.shortcuts import create_sessions_shortcut


class ShortReadStream(BytesIO):
    def read(self, size: int = -1) -> bytes:
        return super().read(min(size, 2) if size >= 0 else 2)


class WorkspaceCliParserTests(unittest.TestCase):
    def test_manifest_ids_become_valid_memory_record_ids(self) -> None:
        self.assertEqual(
            _checkpoint_memory_id("manifest-19f7330bcb0-7a60"),
            "memory_node:manifest_19f7330bcb0_7a60",
        )

    def test_core_commands_need_no_paths_or_session_ids(self) -> None:
        parser = build_parser()

        memory = parser.parse_args(["workspace", "memory", "create"])
        session = parser.parse_args(["workspace", "session", "create"])
        status = parser.parse_args(["workspace", "session", "status"])

        self.assertEqual(memory.workspace_action, "create")
        self.assertEqual(session.memory, [])
        self.assertIsNone(status.session)

    def test_exec_command_does_not_replace_top_level_command(self) -> None:
        args = build_parser().parse_args(
            ["workspace", "session", "exec", "--", "tool", "arg"],
        )

        self.assertEqual(args.command, "workspace")
        self.assertEqual(args.exec_command, ["--", "tool", "arg"])

    def test_shortcut_command_needs_no_path(self) -> None:
        args = build_parser().parse_args(["workspace", "session", "shortcut"])

        self.assertEqual(args.workspace_action, "shortcut")

    def test_plain_session_does_not_implicitly_project_the_repository(self) -> None:
        with mock.patch(
            "reframe_agent_host.commands.workspace.open_memory_database",
            side_effect=AssertionError("empty sessions must not open the memory graph"),
        ):
            resolved = asyncio.run(_resolve_memory_sources([], []))

        self.assertEqual(resolved, [])


class WorkspaceProtocolTests(unittest.TestCase):
    def test_frame_round_trip(self) -> None:
        stream = BytesIO()
        payload = {"request_id": "one", "operation": "health"}

        _write_frame(stream, payload)
        stream.seek(0)

        self.assertEqual(_read_frame(stream), payload)

    def test_frame_reader_handles_short_pipe_reads(self) -> None:
        encoded = BytesIO()
        payload = {"request_id": "two", "operation": "health"}
        _write_frame(encoded, payload)

        stream = ShortReadStream(encoded.getvalue())

        self.assertEqual(_read_frame(stream), payload)

    def test_backing_service_comes_from_uv_environment_path(self) -> None:
        with mock.patch(
            "reframe_agent_host.workspace.service.shutil.which",
            return_value="D:\\project\\.venv\\Scripts\\reframe-workspace-daemon.exe",
        ):
            command = backing_service_command(Path("D:\\workspace-store"))

        self.assertEqual(command[0], "D:\\project\\.venv\\Scripts\\reframe-workspace-daemon.exe")
        self.assertEqual(command[-1], "serve-socket")

    def test_closed_latest_session_is_not_silently_skipped(self) -> None:
        daemon = _FakeDaemon(
            [
                _summary("new", "closed", 2),
                _summary("old", "active", 1),
            ]
        )

        with self.assertRaises(WorkspaceError):
            _latest_summary(daemon, active_only=True)

    def test_unix_shortcut_is_generated_for_the_current_clone(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "data" / "sessions"
            with mock.patch(
                "reframe_agent_host.workspace.shortcuts._create_directory_link"
            ) as create_link:
                result = create_sessions_shortcut(
                    repository=root,
                    sessions=sessions,
                    platform="linux",
                )

            self.assertEqual(result, root / "Agent Sessions")
            create_link.assert_called_once_with(result, sessions.resolve())


class _FakeDaemon:
    def __init__(self, summaries) -> None:
        self.summaries = summaries

    def request(self, operation: str, **_arguments):
        if operation != "list_workspaces":
            raise AssertionError(operation)
        return self.summaries


def _summary(session_id: str, state: str, created_at: int) -> dict:
    return {
        "session_id": session_id,
        "name": "Agent task session",
        "state": state,
        "head_manifest": None,
        "memory_ids": ["memory_node:project"],
        "created_at": created_at,
        "updated_at": created_at,
    }


if __name__ == "__main__":
    unittest.main()
