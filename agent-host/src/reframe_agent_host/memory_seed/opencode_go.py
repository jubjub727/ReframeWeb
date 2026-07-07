from __future__ import annotations

from dataclasses import dataclass

from reframe_agent_host.memory_seed.opencode_go_models import (
    OPENCODE_GO_BASE_URL,
    OpenCodeGoModelReference,
    opencode_go_model_inventory,
)
from reframe_memory.ids import memory_node_record_id
from reframe_memory import (
    MemoryDatabase,
    Provider,
    ProviderNode,
    ProviderSearch,
    TagSearch,
)


DIRECT_MODEL_TAGS = ("opencode-go", "model", "direct-model")
WORKSPACE_MODEL_TAGS = ("opencode-go", "model", "workspace-model")


@dataclass(frozen=True)
class OpenCodeGoProviderSeedResult:
    created_provider_ids: tuple[str, ...]
    existing_provider_ids: tuple[str, ...]
    removed_provider_ids: tuple[str, ...]


async def ensure_opencode_go_providers(
    database: MemoryDatabase,
) -> OpenCodeGoProviderSeedResult:
    created_provider_ids: list[str] = []
    existing_provider_ids: list[str] = []
    for reference in opencode_go_model_inventory():
        direct_default = await _ensure_provider(
            database,
            _direct_provider(reference, None),
            DIRECT_MODEL_TAGS + (reference.model_id,),
        )
        _record_seed_result(direct_default, created_provider_ids, existing_provider_ids)

        for effort in reference.reasoning_efforts:
            direct = await _ensure_provider(
                database,
                _direct_provider(reference, effort),
                DIRECT_MODEL_TAGS + (reference.model_id, effort),
            )
            _record_seed_result(direct, created_provider_ids, existing_provider_ids)

        workspace = await _ensure_provider(
            database,
            _workspace_provider(reference),
            WORKSPACE_MODEL_TAGS + (reference.model_id,),
        )
        _record_seed_result(workspace, created_provider_ids, existing_provider_ids)

    removed_provider_ids = await _prune_removed_providers(database)
    return OpenCodeGoProviderSeedResult(
        created_provider_ids=tuple(created_provider_ids),
        existing_provider_ids=tuple(existing_provider_ids),
        removed_provider_ids=tuple(removed_provider_ids),
    )


async def _ensure_provider(
    database: MemoryDatabase,
    provider: Provider,
    tags: tuple[str, ...],
) -> tuple[ProviderNode, bool]:
    existing = await database.providers.search(
        ProviderSearch.build(
            names=(provider.name,),
            baml_surfaces=(provider.baml_surface,),
            model_ids=(provider.model_id or "",),
            reasoning_efforts=(provider.reasoning_effort or "",),
        )
    )
    for node in existing:
        if (
            node.content.name == provider.name
            and node.content.baml_surface == provider.baml_surface
            and node.content.model_id == provider.model_id
            and node.content.reasoning_effort == provider.reasoning_effort
        ):
            if node.content != provider or tuple(node.tags) != tuple(tags):
                node = await database.providers.update(node.id, provider, tags=tags)
            return node, False

    return await database.providers.create(provider, tags=tags), True


def _record_seed_result(
    provider: tuple[ProviderNode, bool],
    created_provider_ids: list[str],
    existing_provider_ids: list[str],
) -> None:
    node, created = provider
    if created:
        created_provider_ids.append(node.id)
    else:
        existing_provider_ids.append(node.id)


def _direct_provider(reference: OpenCodeGoModelReference, effort: str | None) -> Provider:
    if effort is None:
        return Provider(
            name=f"OpenCode Go direct model: {reference.model_id}",
            description=(
                "Calls the OpenCode Go OpenAI-compatible API directly with model "
                f"{reference.model_id} and no explicit reasoning effort."
            ),
            baml_surface=reference.direct_baml_surface,
            model_id=reference.model_id,
        )

    return Provider(
        name=f"OpenCode Go direct model: {reference.model_id} / {effort}",
        description=(
            "Calls the OpenCode Go OpenAI-compatible API directly with model "
            f"{reference.model_id} and reasoning effort {effort}."
        ),
        baml_surface=reference.direct_baml_surface,
        model_id=reference.model_id,
        reasoning_effort=effort,
    )


def _workspace_provider(reference: OpenCodeGoModelReference) -> Provider:
    return Provider(
        name=f"OpenCode workspace model: {reference.model_id}",
        description=(
            "References the OpenCode binary workspace path for model "
            f"{reference.model_id}. This is not used by direct API benchmarks."
        ),
        baml_surface=reference.workspace_baml_surface,
        model_id=reference.model_id,
    )


async def _prune_removed_providers(database: MemoryDatabase) -> list[str]:
    allowed_keys = _allowed_provider_keys()
    providers = await database.providers.search(
        ProviderSearch.build(tags=TagSearch.build(all_of=("opencode-go",))),
        mark_read=False,
    )
    removed_provider_ids = []
    for provider in providers:
        key = (
            provider.content.baml_surface,
            provider.content.model_id,
            provider.content.reasoning_effort,
        )
        if key in allowed_keys:
            continue
        await _delete_provider(database, provider.id)
        removed_provider_ids.append(provider.id)
    return removed_provider_ids


def _allowed_provider_keys() -> set[tuple[str, str | None, str | None]]:
    keys: set[tuple[str, str | None, str | None]] = set()
    for reference in opencode_go_model_inventory():
        keys.add((reference.direct_baml_surface, reference.model_id, None))
        for effort in reference.reasoning_efforts:
            keys.add((reference.direct_baml_surface, reference.model_id, effort))
        keys.add((reference.workspace_baml_surface, reference.model_id, None))
    return keys


async def _delete_provider(database: MemoryDatabase, provider_id: str) -> None:
    provider_record_id = memory_node_record_id(provider_id)
    await database.query(
        f"""
        DELETE contains WHERE in = memory_root:providers AND out = {provider_record_id};
        DELETE provides_task WHERE in = {provider_record_id};
        DELETE {provider_record_id};
        """,
    )
