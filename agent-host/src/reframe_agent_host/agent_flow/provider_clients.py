from __future__ import annotations

import re
from typing import Any

from baml_sdk import baml as baml_std
from reframe_memory import ProviderNode


BamlClient = baml_std.llm.Client


def compiled_client(name: str) -> BamlClient:
    return baml_std.llm.Client(
        name=name.rsplit(".", 1)[-1],
        client_type=baml_std.llm.ClientType.Primitive,
        sub_clients=[],
        retry=None,
        counter=0,
    )


def client_kwargs(client: BamlClient | str | None) -> dict[str, Any]:
    if client is None:
        return {}
    if isinstance(client, str):
        return {"client": compiled_client(client)}
    return {"client": client}


def provider_client(provider: ProviderNode) -> tuple[BamlClient, str]:
    surface = provider.content.baml_surface
    effort = provider.content.reasoning_effort
    client_name = surface if not effort else surface + "Reasoning" + _identifier(effort)
    return compiled_client(client_name), client_name


def _identifier(value: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", value)
    return "".join(part.capitalize() for part in parts if part) or "Default"
