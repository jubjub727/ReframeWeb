from __future__ import annotations

from dataclasses import dataclass

from reframe_agent_host.memory_seed.core_task_definitions import (
    CORE_TASK_PROVIDER,
    CORE_TASK_TAGS,
    CORE_TASKS,
)
from reframe_memory import (
    MemoryDatabase,
    ProviderNode,
    ProviderSearch,
    TaskNode,
    TaskSearch,
)


@dataclass(frozen=True)
class CoreTaskSeedResult:
    provider_id: str
    created_task_ids: tuple[str, ...]
    existing_task_ids: tuple[str, ...]


async def ensure_core_tasks(database: MemoryDatabase) -> CoreTaskSeedResult:
    provider = await _ensure_provider(database)
    created_task_ids: list[str] = []
    existing_task_ids: list[str] = []
    for definition in CORE_TASKS:
        existing = await _find_task(database, provider.id, definition.name)
        if existing is not None:
            existing_task_ids.append(existing.id)
            continue

        task = await database.tasks.create(
            definition.to_task(provider.id),
            tags=definition.tags,
        )
        created_task_ids.append(task.id)

    return CoreTaskSeedResult(
        provider_id=provider.id,
        created_task_ids=tuple(created_task_ids),
        existing_task_ids=tuple(existing_task_ids),
    )


async def _ensure_provider(database: MemoryDatabase) -> ProviderNode:
    providers = await database.providers.search(
        ProviderSearch.build(
            names=(CORE_TASK_PROVIDER.name,),
            baml_surfaces=(CORE_TASK_PROVIDER.baml_surface,),
        )
    )
    for provider in providers:
        if (
            provider.content.name == CORE_TASK_PROVIDER.name
            and provider.content.baml_surface == CORE_TASK_PROVIDER.baml_surface
        ):
            return provider

    return await database.providers.create(CORE_TASK_PROVIDER, tags=CORE_TASK_TAGS)


async def _find_task(
    database: MemoryDatabase,
    provider_id: str,
    name: str,
) -> TaskNode | None:
    tasks = await database.tasks.search(
        TaskSearch.build(names=(name,), provider_ids=(provider_id,))
    )
    for task in tasks:
        if task.content.name == name and task.content.provider_id == provider_id:
            return task

    return None
