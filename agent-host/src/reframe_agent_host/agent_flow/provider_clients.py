from __future__ import annotations

import os
import re
from typing import Any

from baml_py import ClientRegistry

from reframe_agent_host.baml_client import b
from reframe_agent_host.memory_seed.opencode_go_models import OPENCODE_GO_BASE_URL
from reframe_memory import ProviderNode


def opencode_provider_client(
    provider: ProviderNode,
    extra_options: dict[str, Any] | None = None,
):
    model_id = provider.content.model_id
    if model_id is None:
        msg = f"provider memory has no model_id: {provider.id}"
        raise ValueError(msg)

    client_name = _client_name(model_id, provider.content.reasoning_effort)
    options = {
        "base_url": OPENCODE_GO_BASE_URL,
        "model": model_id,
        "api_key": os.environ.get("OPENCODE_GO_API_KEY", ""),
    }
    if provider.content.reasoning_effort:
        options["reasoning_effort"] = provider.content.reasoning_effort
    if extra_options:
        options.update(extra_options)

    registry = ClientRegistry()
    registry.add_llm_client(client_name, "openai-generic", options)
    registry.set_primary(client_name)
    return b.with_options(client_registry=registry), client_name


def _client_name(model_id: str, effort: str | None) -> str:
    suffix = "Default" if not effort else _identifier(effort)
    return _identifier(model_id) + "Reasoning" + suffix


def _identifier(value: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", value)
    text = "".join(part.capitalize() for part in parts if part)
    return text or "Model"
