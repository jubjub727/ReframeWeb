from __future__ import annotations

from pathlib import Path

from baml_sdk.workspace import (
    FilesystemMemoryReference,
    Materialization,
    Retention,
    WorkspacePlan,
)
from reframe_agent_host.workspace.models import (
    CheckpointMemorySource,
    DirectoryMemorySource,
    MemorySource,
    ResolvedWorkspacePlan,
)
from reframe_agent_host.workspace.errors import WorkspaceError
from reframe_memory import (
    CheckpointFilesystemMemory,
    DirectoryFilesystemMemory,
    MemoryDatabase,
)


async def filesystem_memory_catalog(
    database: MemoryDatabase,
) -> list[FilesystemMemoryReference]:
    nodes = await database.filesystem_memories.list()
    return [
        FilesystemMemoryReference(
            id=node.id,
            title=node.content.title,
            description=node.content.description,
            tags=list(node.tags),
        )
        for node in nodes
    ]


async def resolve_memory_sources(
    database: MemoryDatabase,
    memory_ids: list[str],
) -> list[MemorySource]:
    sources: list[MemorySource] = []
    resolving: set[str] = set()
    resolved: set[str] = set()

    async def resolve(memory_id: str) -> None:
        if memory_id in resolved:
            return
        if memory_id in resolving:
            raise WorkspaceError(f"filesystem memory dependency cycle: {memory_id}")
        resolving.add(memory_id)
        node = await database.filesystem_memories.get(memory_id)
        if node is None:
            raise WorkspaceError(f"filesystem memory does not exist: {memory_id}")
        memory = node.content
        for base_id in memory.base_memory_ids:
            await resolve(base_id)
        if isinstance(memory, DirectoryFilesystemMemory):
            source = Path(memory.source_path).resolve()
            if not source.is_dir():
                raise WorkspaceError(
                    f"filesystem memory source is unavailable: {source} ({memory_id})"
                )
            sources.append(
                DirectoryMemorySource(
                    memory_id=node.id,
                    source_path=str(source),
                )
            )
        elif isinstance(memory, CheckpointFilesystemMemory):
            backing_store = Path(memory.backing_store).resolve()
            if not backing_store.is_dir():
                raise WorkspaceError(
                    f"filesystem memory backing store is unavailable: {backing_store} "
                    f"({memory_id})"
                )
            sources.append(
                CheckpointMemorySource(
                    memory_id=node.id,
                    backing_store=str(backing_store),
                    manifest_id=memory.manifest_id,
                )
            )
        else:
            raise WorkspaceError(
                f"unsupported filesystem memory type: {type(memory).__name__}"
            )
        resolving.remove(memory_id)
        resolved.add(memory_id)

    for memory_id in dict.fromkeys(memory_ids):
        await resolve(memory_id)
    return sources


async def resolve_workspace_plan(
    database: MemoryDatabase,
    plan: WorkspacePlan,
) -> ResolvedWorkspacePlan:
    scratch_paths = workspace_scratch_paths(plan)
    return ResolvedWorkspacePlan(
        memory_sources=await resolve_memory_sources(database, plan.memory_ids),
        prefetch_paths=list(plan.prefetch_paths),
        scratch_paths=scratch_paths,
    )


def workspace_scratch_paths(plan: WorkspacePlan) -> list[str]:
    return [
        rule.path_glob
        for rule in plan.rules
        if rule.materialization == Materialization.DirectDisk
        and rule.retention == Retention.Discard
    ]
