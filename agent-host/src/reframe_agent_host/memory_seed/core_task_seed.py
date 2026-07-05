from __future__ import annotations

from dataclasses import dataclass

from reframe_agent_host.memory_seed.core_task_definitions import (
    CORE_TASK_MODEL_ID,
    CORE_TASK_REASONING_EFFORT,
    CORE_TASKS,
)
from reframe_agent_host.memory_seed.opencode_go import (
    DIRECT_MODEL_TAGS,
    ensure_opencode_go_providers,
)
from reframe_memory import (
    MemoryDatabase,
    ProviderNode,
    ProviderSearch,
    TagSearch,
    TaskNode,
    TaskSearch,
)


@dataclass(frozen=True)
class CoreTaskSeedResult:
    provider_id: str
    created_task_ids: tuple[str, ...]
    existing_task_ids: tuple[str, ...]
    updated_task_ids: tuple[str, ...]


async def ensure_core_tasks(database: MemoryDatabase) -> CoreTaskSeedResult:
    provider = await _ensure_provider(database)
    created_task_ids: list[str] = []
    existing_task_ids: list[str] = []
    updated_task_ids: list[str] = []
    for definition in CORE_TASKS:
        expected = definition.to_task(provider.id)
        existing = await _find_task(database, definition.name)
        if existing is not None:
            if existing.content != expected or existing.tags != definition.tags:
                task = await database.tasks.update(
                    existing.id,
                    expected,
                    tags=definition.tags,
                )
                updated_task_ids.append(task.id)
                continue
            existing_task_ids.append(existing.id)
            continue

        task = await database.tasks.create(
            expected,
            tags=definition.tags,
        )
        created_task_ids.append(task.id)

    return CoreTaskSeedResult(
        provider_id=provider.id,
        created_task_ids=tuple(created_task_ids),
        existing_task_ids=tuple(existing_task_ids),
        updated_task_ids=tuple(updated_task_ids),
    )


async def _ensure_provider(database: MemoryDatabase) -> ProviderNode:
    await ensure_opencode_go_providers(database)
    providers = await database.providers.search(
        ProviderSearch.build(
            tags=TagSearch.build(
                all_of=DIRECT_MODEL_TAGS
                + (CORE_TASK_MODEL_ID, CORE_TASK_REASONING_EFFORT),
            ),
            model_ids=(CORE_TASK_MODEL_ID,),
            reasoning_efforts=(CORE_TASK_REASONING_EFFORT,),
        ),
        mark_read=False,
    )
    for provider in providers:
        if (
            provider.content.model_id == CORE_TASK_MODEL_ID
            and provider.content.reasoning_effort == CORE_TASK_REASONING_EFFORT
        ):
            return provider

    msg = (
        "core task provider was not seeded: "
        f"{CORE_TASK_MODEL_ID}/{CORE_TASK_REASONING_EFFORT}"
    )
    raise ValueError(msg)


async def _find_task(
    database: MemoryDatabase,
    name: str,
) -> TaskNode | None:
    tasks = await database.tasks.search(
        TaskSearch.build(names=(name,)),
        mark_read=False,
    )
    for task in tasks:
        if task.content.name == name:
            return task

    return None
