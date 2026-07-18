from __future__ import annotations

import asyncio
from contextlib import redirect_stderr
from io import BytesIO
from io import StringIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from baml_sdk.workspace import WorkspacePlan
from reframe_agent_host.commands.parser import build_parser
from reframe_agent_host.commands.workspace_args import build_workspace_parser
from reframe_agent_host.workspace.coordinator import WorkspaceCoordinator
from reframe_agent_host.workspace import WorkspaceError
from reframe_agent_host.workspace.service import (
    _read_frame,
    _write_frame,
)
from reframe_agent_host.workspace.daemon_process import backing_service_command
from reframe_agent_host.workspace.shortcuts import create_sessions_shortcut


class ShortReadStream(BytesIO):
    def read(self, size: int = -1) -> bytes:
        return super().read(min(size, 2) if size >= 0 else 2)


class WorkspaceCliParserTests(unittest.TestCase):
    def test_workspace_help_displays_the_winfsp_notice(self) -> None:
        stdout = StringIO()
        with self.assertRaises(SystemExit), mock.patch("sys.stdout", stdout):
            build_workspace_parser().parse_args(["workspace", "--help"])

        self.assertIn("WinFsp - Windows File System Proxy", stdout.getvalue())
        self.assertIn("https://github.com/winfsp/winfsp", stdout.getvalue())

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

    def test_session_create_rejects_memory_with_continue(self) -> None:
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as raised:
                build_parser().parse_args(
                    [
                        "workspace",
                        "session",
                        "create",
                        "--memory",
                        "memory_node:project",
                        "--continue",
                    ]
                )

        self.assertEqual(raised.exception.code, 2)

    def test_plain_session_does_not_implicitly_project_the_repository(self) -> None:
        daemon = _FakeDaemon([])

        async def no_database():
            raise AssertionError("empty sessions must not open the memory graph")

        async def manual_plan(memory_ids, prefetch_paths, _scratch):
            return WorkspacePlan(
                memory_ids=memory_ids,
                prefetch_paths=prefetch_paths,
                rules=[],
            )

        coordinator = WorkspaceCoordinator(
            daemon,
            database_factory=no_database,
            workspace_plan=manual_plan,
        )
        created = asyncio.run(
            coordinator.create_session(memory_ids=[], continue_session=None)
        )

        self.assertEqual(created.memory_ids, [])
        self.assertEqual(daemon.created_memory_sources, [])


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
            "reframe_agent_host.workspace.daemon_process.shutil.which",
            return_value="D:\\project\\.venv\\Scripts\\reframe-workspace-daemon.exe",
        ):
            command = backing_service_command(Path("D:\\workspace-store"))

        self.assertEqual(command[0], "D:\\project\\.venv\\Scripts\\reframe-workspace-daemon.exe")
        self.assertEqual(command[-1], "serve-socket")

    def test_backing_service_falls_back_to_the_interpreter_environment(self) -> None:
        with TemporaryDirectory() as temporary:
            scripts = Path(temporary) / "Scripts"
            scripts.mkdir()
            name = (
                "reframe-workspace-daemon.exe"
                if os.name == "nt"
                else "reframe-workspace-daemon"
            )
            executable = scripts / name
            executable.touch()
            executable.chmod(0o755)

            with (
                mock.patch(
                    "reframe_agent_host.workspace.daemon_process.shutil.which",
                    return_value=None,
                ),
                mock.patch(
                    "reframe_agent_host.workspace.daemon_process.sys.executable",
                    str(scripts / "python.exe"),
                ),
                mock.patch(
                    "reframe_agent_host.workspace.daemon_process.sysconfig.get_path",
                    return_value=str(scripts),
                ),
            ):
                command = backing_service_command(Path(temporary) / "store")

        self.assertEqual(Path(command[0]), executable.resolve())
        self.assertEqual(command[-1], "serve-socket")

    def test_closed_latest_session_is_not_silently_skipped(self) -> None:
        daemon = _FakeDaemon(
            [
                _summary("new", "closed", 2),
                _summary("old", "active", 1),
            ]
        )

        with self.assertRaises(WorkspaceError):
            asyncio.run(
                WorkspaceCoordinator(daemon).latest_summary(require_active=True)
            )

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
        self.created_memory_sources = None
        self.store = Path("D:/workspace-store")

    def list_workspaces(self, *, active_only: bool = False):
        del active_only
        return self.summaries

    def create_workspace(
        self,
        *,
        name,
        session_id,
        memory_sources,
        scratch_paths,
    ):
        del name, session_id, scratch_paths
        self.created_memory_sources = list(memory_sources)
        return {
            "session_id": "task-one",
            "worktree": "D:/workspace-store/sessions/task-one/worktree",
            "memory_ids": [],
            "projected_files": 0,
        }


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
