from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from baml_sdk.workspace import CheckpointSelection, WorkspacePlan
from reframe_agent_host.workspace import WorkspaceError
from reframe_agent_host.workspace.coordinator import WorkspaceCoordinator
from reframe_memory import MemoryNode, MemoryTimestamps
from reframe_memory.filesystem_memories import filesystem_checkpoint_memory_id


class WorkspaceCoordinatorTests(unittest.TestCase):
    def test_generated_baml_plan_is_used_by_the_production_coordinator(self) -> None:
        with TemporaryDirectory() as temporary:
            daemon = _FakeDaemon(Path(temporary))

            async def no_database():
                raise AssertionError("an empty BAML plan must not open the graph")

            created = asyncio.run(
                WorkspaceCoordinator(
                    daemon,
                    database_factory=no_database,
                ).create_session(memory_ids=[], continue_session=None)
            )

            self.assertEqual(created.session_id, "task-created")
            self.assertEqual(daemon.created_sources, [])

    def test_session_prefetch_runs_while_the_new_workspace_is_mounted(self) -> None:
        with TemporaryDirectory() as temporary:
            daemon = _FakeDaemon(Path(temporary))

            async def workspace_plan(memory_ids, _prefetch_paths, _scratch_globs):
                return WorkspacePlan(
                    memory_ids=memory_ids,
                    prefetch_paths=["README.md", "src/main.rs"],
                    rules=[],
                )

            created = asyncio.run(
                WorkspaceCoordinator(
                    daemon,
                    workspace_plan=workspace_plan,
                ).create_session(memory_ids=[], continue_session=None)
            )

            self.assertEqual(created.session_id, "task-created")
            self.assertEqual(
                daemon.lifecycle,
                [
                    ("create", "task-created"),
                    ("mount", "task-created"),
                    ("prefetch", "task-created", ("README.md", "src/main.rs")),
                    ("unmount", "task-created"),
                ],
            )

    def test_created_session_is_recoverable_when_prefetch_lifecycle_fails(self) -> None:
        async def workspace_plan(memory_ids, _prefetch_paths, _scratch_globs):
            return WorkspacePlan(
                memory_ids=memory_ids,
                prefetch_paths=["README.md"],
                rules=[],
            )

        for failure in ("mount", "prefetch", "unmount"):
            with self.subTest(failure=failure), TemporaryDirectory() as temporary:
                daemon = _FakeDaemon(Path(temporary), fail_lifecycle=failure)
                coordinator = WorkspaceCoordinator(
                    daemon,
                    workspace_plan=workspace_plan,
                )

                with self.assertRaisesRegex(
                    WorkspaceError,
                    "task-created.*remains active and recoverable",
                ):
                    asyncio.run(
                        coordinator.create_session(
                            memory_ids=[],
                            continue_session=None,
                        )
                    )

                self.assertEqual(daemon.lifecycle[0], ("create", "task-created"))

    def test_memory_and_continue_are_rejected_before_creating_a_session(self) -> None:
        with TemporaryDirectory() as temporary:
            daemon = _FakeDaemon(Path(temporary))
            coordinator = WorkspaceCoordinator(daemon)

            with self.assertRaisesRegex(
                WorkspaceError,
                "--memory cannot be combined with --continue",
            ):
                asyncio.run(
                    coordinator.create_session(
                        memory_ids=["memory_node:project"],
                        continue_session="latest",
                    )
                )

            self.assertEqual(daemon.lifecycle, [])

    def test_checkpoint_uses_baml_selection_and_completes_outbox(self) -> None:
        with TemporaryDirectory() as temporary:
            daemon = _FakeDaemon(Path(temporary))
            database = _FakeDatabase()
            selected: list[list[str]] = []

            async def checkpoint_selection(paths):
                selected.append(paths)
                return CheckpointSelection(
                    paths=["src/result.rs"],
                    reasons={"src/result.rs": "selected in test"},
                )

            coordinator = WorkspaceCoordinator(
                daemon,
                database_factory=lambda: _ready(database),
                checkpoint_selection=checkpoint_selection,
            )
            result = asyncio.run(
                coordinator.checkpoint(
                    None,
                    paths=["raw-path"],
                    retain_all=False,
                )
            )

            self.assertEqual(selected, [["raw-path"]])
            self.assertEqual(daemon.checkpoint_paths, ["src/result.rs"])
            self.assertEqual(
                result.memory_id,
                filesystem_checkpoint_memory_id(temporary, "manifest-one"),
            )
            self.assertEqual(daemon.pending, [])

    def test_failed_graph_publication_is_reconciled_on_a_later_run(self) -> None:
        with TemporaryDirectory() as temporary:
            daemon = _FakeDaemon(Path(temporary))
            failing = _FakeDatabase(fail_publication=True)
            coordinator = WorkspaceCoordinator(
                daemon,
                database_factory=lambda: _ready(failing),
                checkpoint_selection=_manual_checkpoint,
            )

            with self.assertRaisesRegex(WorkspaceError, "memory publication remains pending"):
                asyncio.run(
                    coordinator.checkpoint(
                        None,
                        paths=["src/result.rs"],
                        retain_all=False,
                    )
                )

            self.assertEqual(len(daemon.pending), 1)
            recovered = _FakeDatabase()
            recovery = WorkspaceCoordinator(
                daemon,
                database_factory=lambda: _ready(recovered),
            )
            count = asyncio.run(recovery.reconcile_pending_publications(strict=True))

            self.assertEqual(count, 1)
            self.assertEqual(daemon.pending, [])
            self.assertEqual(len(recovered.filesystem_memories.published), 1)
            self.assertEqual(
                asyncio.run(recovery.reconcile_pending_publications(strict=True)),
                0,
            )

    def test_daemon_outbox_recovers_a_crash_before_python_publication(self) -> None:
        with TemporaryDirectory() as temporary:
            daemon = _FakeDaemon(Path(temporary))
            daemon.add_pending_publication("manifest-crash", retained_count=1)
            database = _FakeDatabase()
            coordinator = WorkspaceCoordinator(
                daemon,
                database_factory=lambda: _ready(database),
            )

            count = asyncio.run(coordinator.reconcile_pending_publications(strict=True))

            self.assertEqual(count, 1)
            self.assertEqual(daemon.pending, [])
            self.assertEqual(
                daemon.completed,
                [
                    (
                        "manifest-crash",
                        filesystem_checkpoint_memory_id(
                            temporary,
                            "manifest-crash",
                        ),
                    )
                ],
            )

    def test_non_strict_reconciliation_logs_failures_and_keeps_retrying(self) -> None:
        with TemporaryDirectory() as temporary:
            daemon = _FakeDaemon(Path(temporary))
            daemon.add_pending_publication("manifest-retry", retained_count=1)
            coordinator = WorkspaceCoordinator(
                daemon,
                database_factory=lambda: _ready(
                    _FakeDatabase(fail_publication=True)
                ),
            )

            with self.assertLogs(
                "reframe_agent_host.workspace.publication_service",
                level="WARNING",
            ) as captured:
                count = asyncio.run(coordinator.reconcile_pending_publications())

            self.assertEqual(count, 0)
            self.assertEqual(len(daemon.pending), 1)
            self.assertIn("manifest-retry", "\n".join(captured.output))
            self.assertIn("remains queued for retry", "\n".join(captured.output))


class _FakeDaemon:
    def __init__(self, store: Path, *, fail_lifecycle: str | None = None) -> None:
        self.store = store
        self.fail_lifecycle = fail_lifecycle
        self.checkpoint_paths: list[str] = []
        self.created_sources = None
        self.pending: list[dict] = []
        self.completed: list[tuple[str, str]] = []
        self.lifecycle: list[tuple] = []

    def create_workspace(
        self,
        *,
        name,
        session_id,
        memory_sources,
        scratch_paths,
    ):
        del name, session_id, scratch_paths
        self.created_sources = list(memory_sources)
        self.lifecycle.append(("create", "task-created"))
        return {
            "session_id": "task-created",
            "worktree": str(self.store / "sessions" / "task-created" / "worktree"),
            "memory_ids": [],
            "projected_files": 0,
        }

    def mount_workspace(self, session_id: str):
        self.lifecycle.append(("mount", session_id))
        if self.fail_lifecycle == "mount":
            raise WorkspaceError("injected mount failure")
        return {"session_id": session_id}

    def prefetch(self, session_id: str, paths):
        self.lifecycle.append(("prefetch", session_id, tuple(paths)))
        if self.fail_lifecycle == "prefetch":
            raise WorkspaceError("injected prefetch failure")
        return {"session_id": session_id, "files": len(paths), "bytes": 0}

    def unmount_workspace(self, session_id: str):
        self.lifecycle.append(("unmount", session_id))
        if self.fail_lifecycle == "unmount":
            raise WorkspaceError("injected unmount failure")
        return {"session_id": session_id}

    def list_workspaces(self, *, active_only: bool = False):
        del active_only
        return [
            {
                "session_id": "task-one",
                "name": "Agent task session",
                "state": "active",
                "head_manifest": None,
                "memory_ids": ["memory_node:project"],
                "created_at": 1,
                "updated_at": 1,
            }
        ]

    def commit_checkpoint(self, session_id, *, paths, all):
        del session_id, all
        self.checkpoint_paths = list(paths)
        self.add_pending_publication("manifest-one", retained_count=len(paths))
        return {
            "session_id": "task-one",
            "manifest_id": "manifest-one",
            "retained_paths": list(paths),
            "remaining_changes": [],
        }

    def add_pending_publication(self, manifest_id: str, *, retained_count: int) -> None:
        self.pending.append(
            {
                "manifest_id": manifest_id,
                "session_id": "task-one",
                "session_name": "Agent task session",
                "base_memory_ids": ["memory_node:project"],
                "retained_count": retained_count,
            }
        )

    def list_pending_checkpoint_publications(self):
        return list(self.pending)

    def complete_checkpoint_publication(self, manifest_id: str, memory_id: str):
        self.completed.append((manifest_id, memory_id))
        self.pending = [
            publication
            for publication in self.pending
            if publication["manifest_id"] != manifest_id
        ]
        return {
            "manifest_id": manifest_id,
            "memory_id": memory_id,
            "published": True,
        }


class _FakeFilesystemMemories:
    def __init__(self, *, fail_publication: bool) -> None:
        self.fail_publication = fail_publication
        self.published = []

    async def ensure_root(self) -> None:
        pass

    async def publish_checkpoint(self, memory, tags=()):
        if self.fail_publication:
            raise RuntimeError("graph unavailable")
        self.published.append((memory, tags))
        now = datetime.now(timezone.utc)
        return MemoryNode(
            id=filesystem_checkpoint_memory_id(
                memory.backing_store,
                memory.manifest_id,
            ),
            tags=tuple(tags),
            timestamps=MemoryTimestamps(now, now, None),
            content=memory,
        )


class _FakeDatabase:
    def __init__(self, *, fail_publication: bool = False) -> None:
        self.filesystem_memories = _FakeFilesystemMemories(
            fail_publication=fail_publication
        )

    async def apply_schema(self) -> None:
        pass

    async def close(self) -> None:
        pass


async def _ready(value):
    return value


async def _manual_checkpoint(paths):
    return CheckpointSelection(
        paths=list(paths),
        reasons={path: "manually selected" for path in paths},
    )


if __name__ == "__main__":
    unittest.main()
