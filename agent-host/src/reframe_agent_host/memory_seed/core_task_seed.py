from __future__ import annotations

from dataclasses import dataclass

from reframe_agent_host.memory_seed.core_task_definitions import (
    CORE_TASKS,
    CoreTaskDefinition,
)
from reframe_agent_host.magic_providers import (
    MAGIC_DO_NOTHING_MODEL_ID,
    MAGIC_DO_NOTHING_TAGS,
    magic_do_nothing_provider,
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
    provider_ids: tuple[str, ...]
    created_task_ids: tuple[str, ...]
    existing_task_ids: tuple[str, ...]
    updated_task_ids: tuple[str, ...]


async def ensure_core_tasks(database: MemoryDatabase) -> CoreTaskSeedResult:
    await ensure_opencode_go_providers(database)
    await _ensure_magic_providers(database)
    providers: dict[tuple[str, str | None], ProviderNode] = {}
    created_task_ids: list[str] = []
    existing_task_ids: list[str] = []
    updated_task_ids: list[str] = []
    for definition in CORE_TASKS:
        provider = providers.get((definition.model_id, definition.reasoning_effort))
        if provider is None:
            provider = await _provider_for_definition(database, definition)
            providers[(definition.model_id, definition.reasoning_effort)] = provider
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

    provider_ids = tuple(provider.id for provider in providers.values())
    return CoreTaskSeedResult(
        provider_ids=provider_ids,
        created_task_ids=tuple(created_task_ids),
        existing_task_ids=tuple(existing_task_ids),
        updated_task_ids=tuple(updated_task_ids),
    )


async def _provider_for_definition(
    database: MemoryDatabase,
    definition: CoreTaskDefinition,
) -> ProviderNode:
    if definition.model_id == MAGIC_DO_NOTHING_MODEL_ID:
        return await _magic_do_nothing_provider(database)

    providers = await database.providers.search(
        ProviderSearch.build(
            tags=TagSearch.build(
                all_of=DIRECT_MODEL_TAGS + (definition.model_id,),
            ),
            model_ids=(definition.model_id,),
            reasoning_efforts=_reasoning_effort_search(definition.reasoning_effort),
        ),
        mark_read=False,
    )
    for provider in providers:
        if (
            provider.content.model_id == definition.model_id
            and provider.content.reasoning_effort == definition.reasoning_effort
        ):
            return provider

    msg = (
        "core task provider was not seeded: "
        f"{definition.model_id}/{definition.reasoning_effort or 'default'}"
    )
    raise ValueError(msg)


async def _ensure_magic_providers(database: MemoryDatabase) -> None:
    provider = magic_do_nothing_provider()
    existing = await database.providers.search(
        ProviderSearch.build(
            model_ids=(MAGIC_DO_NOTHING_MODEL_ID,),
        ),
        mark_read=False,
    )
    for node in existing:
        if (
            node.content.baml_surface == provider.baml_surface
            and node.content.model_id == provider.model_id
            and node.content.reasoning_effort == provider.reasoning_effort
        ):
            if node.content != provider or tuple(node.tags) != MAGIC_DO_NOTHING_TAGS:
                await database.providers.update(
                    node.id,
                    provider,
                    tags=MAGIC_DO_NOTHING_TAGS,
                )
            return

    await database.providers.create(provider, tags=MAGIC_DO_NOTHING_TAGS)


async def _magic_do_nothing_provider(database: MemoryDatabase) -> ProviderNode:
    providers = await database.providers.search(
        ProviderSearch.build(
            tags=TagSearch.build(all_of=MAGIC_DO_NOTHING_TAGS),
            model_ids=(MAGIC_DO_NOTHING_MODEL_ID,),
        ),
        mark_read=False,
    )
    expected = magic_do_nothing_provider()
    for provider in providers:
        if (
            provider.content.baml_surface == expected.baml_surface
            and provider.content.model_id == expected.model_id
            and provider.content.reasoning_effort == expected.reasoning_effort
        ):
            return provider

    raise ValueError("magic do-nothing provider was not seeded")


def _reasoning_effort_search(reasoning_effort: str | None) -> tuple[str, ...]:
    if reasoning_effort is None:
        return ()
    return (reasoning_effort,)


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
