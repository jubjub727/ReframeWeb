from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from baml_sdk.workspace import (
    Materialization,
    Retention,
    WorkspacePlan,
    WorkspacePolicyRule,
)
from reframe_agent_host.workspace.planning import (
    filesystem_memory_catalog,
    resolve_workspace_plan,
)
from reframe_memory import FilesystemMemory, MemoryNode, MemoryTimestamps


class WorkspacePlanningTests(unittest.IsolatedAsyncioTestCase):
    async def test_baml_plan_resolves_through_python_memory_host(self) -> None:
        with TemporaryDirectory() as source:
            database = _FakeDatabase(_node(source))
            plan = WorkspacePlan(
                memory_ids=["memory_node:design"],
                prefetch_paths=["README.md"],
                rules=[
                    WorkspacePolicyRule(
                        path_glob="node_modules",
                        materialization=Materialization.DirectDisk,
                        retention=Retention.Discard,
                        provenance="manual",
                    )
                ],
            )

            resolved = await resolve_workspace_plan(database, plan)

            self.assertEqual(
                resolved.memory_sources[0].source_path,
                str(Path(source).resolve()),
            )
            self.assertEqual(resolved.memory_sources[0].source_kind, "directory")
            self.assertEqual(resolved.prefetch_paths, ["README.md"])
            self.assertEqual(resolved.scratch_paths, ["node_modules"])

    async def test_catalog_exposes_memory_metadata_without_source_paths(self) -> None:
        database = _FakeDatabase(_node(r"D:\private\source"))

        catalog = await filesystem_memory_catalog(database)

        self.assertEqual(catalog[0].id, "memory_node:design")
        self.assertEqual(catalog[0].title, "Design")
        self.assertFalse(hasattr(catalog[0], "source_path"))


class _FakeFilesystemMemories:
    def __init__(self, node: MemoryNode[FilesystemMemory]) -> None:
        self.node = node

    async def get(self, memory_id: str):
        return self.node if memory_id == self.node.id else None

    async def list(self):
        return [self.node]


class _FakeDatabase:
    def __init__(self, node: MemoryNode[FilesystemMemory]) -> None:
        self.filesystem_memories = _FakeFilesystemMemories(node)


def _node(source_path: str) -> MemoryNode[FilesystemMemory]:
    now = datetime.now(timezone.utc)
    return MemoryNode(
        id="memory_node:design",
        tags=("workspace",),
        timestamps=MemoryTimestamps(now, now, None),
        content=FilesystemMemory(
            title="Design",
            description="Workspace design memory",
            source_kind="directory",
            source_path=source_path,
        ),
    )


if __name__ == "__main__":
    unittest.main()
