from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from contextlib import asynccontextmanager

from baml_sdk.workspace import ManualWorkspacePlan_async, WorkspacePlan
from reframe_agent_host.workspace.location import project_root
from reframe_agent_host.workspace.models import ResolvedWorkspacePlan
from reframe_agent_host.workspace.planning import (
    resolve_workspace_plan,
    workspace_scratch_paths,
)
from reframe_memory import (
    DirectoryFilesystemMemory,
    FilesystemMemoryNode,
    MemoryDatabase,
)


DatabaseFactory = Callable[[], Awaitable[MemoryDatabase]]
WorkspacePlanFunction = Callable[..., Awaitable[WorkspacePlan]]


class WorkspaceMemoryService:
    def __init__(
        self,
        database_factory: DatabaseFactory,
        workspace_plan: WorkspacePlanFunction = ManualWorkspacePlan_async,
    ) -> None:
        self._database_factory = database_factory
        self._workspace_plan = workspace_plan

    async def create_project_memory(self) -> FilesystemMemoryNode:
        source = project_root().resolve()
        memory = DirectoryFilesystemMemory(
            title=source.name,
            description=f"Filesystem memory for the {source.name} project",
            source_path=str(source),
        )
        async with self._database() as database:
            await database.apply_schema()
            await database.filesystem_memories.ensure_root()
            return await database.filesystem_memories.publish_directory(
                memory,
                tags=("workspace",),
            )

    async def list_memories(self) -> list[FilesystemMemoryNode]:
        async with self._database() as database:
            await database.apply_schema()
            await database.filesystem_memories.ensure_root()
            return await database.filesystem_memories.list()

    async def resolve_plan(self, memory_ids: Sequence[str]) -> ResolvedWorkspacePlan:
        plan = await self._workspace_plan(list(memory_ids), [], [])
        if not plan.memory_ids:
            return ResolvedWorkspacePlan(
                memory_sources=[],
                prefetch_paths=list(plan.prefetch_paths),
                scratch_paths=workspace_scratch_paths(plan),
            )
        async with self._database() as database:
            return await resolve_workspace_plan(database, plan)

    @asynccontextmanager
    async def _database(self):
        database = await self._database_factory()
        try:
            yield database
        finally:
            await database.close()
