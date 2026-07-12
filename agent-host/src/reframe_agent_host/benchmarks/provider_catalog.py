from __future__ import annotations

from baml_sdk import opencode_go as baml_opencode_go

from reframe_agent_host.memory_seed.opencode_go import DIRECT_MODEL_TAGS
from reframe_memory import MemoryDatabase, ProviderNode, ProviderSearch, TagSearch


async def direct_model_providers(
    database: MemoryDatabase,
    provider_ids: tuple[str, ...],
) -> tuple[ProviderNode, ...]:
    providers = await database.providers.search(
        ProviderSearch.build(tags=TagSearch.build(all_of=DIRECT_MODEL_TAGS))
    )
    direct_surfaces = {
        reference.direct_baml_surface for reference in baml_opencode_go.ModelInventory()
    }
    providers = [
        provider
        for provider in providers
        if provider.content.baml_surface in direct_surfaces
    ]
    if provider_ids:
        wanted = set(provider_ids)
        providers = [provider for provider in providers if provider.id in wanted]
        found = {provider.id for provider in providers}
        missing = sorted(wanted - found)
        if missing:
            raise ValueError(
                "unknown direct model provider ids: " + ", ".join(missing)
            )
    return tuple(
        sorted(providers, key=lambda provider: provider.content.baml_surface.lower())
    )


def model_id_for_surface(surface: str) -> str | None:
    for reference in baml_opencode_go.ModelInventory():
        if reference.direct_baml_surface == surface:
            return reference.model_id
    return None
