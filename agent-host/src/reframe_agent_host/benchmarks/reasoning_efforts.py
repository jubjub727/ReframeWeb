from __future__ import annotations

import re

from baml_core import Collector
from baml_sdk import benchmarks as baml_benchmarks
from baml_sdk import opencode_go as baml_opencode_go

from reframe_agent_host.agent_flow.provider_clients import (
    BamlClient,
    compiled_client,
)
from reframe_agent_host.benchmarks.provider_catalog import (
    model_id_for_surface,
)
from reframe_memory import ProviderNode


OPENCODE_GO_REASONING_EFFORT_CANDIDATES = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)


def opencode_reasoning_effort_candidates(
    provider: ProviderNode,
    candidates: tuple[str, ...],
) -> tuple[str, ...]:
    supported = _reasoning_efforts_for_surface(provider.content.baml_surface)
    if supported is None:
        return candidates
    return tuple(candidate for candidate in candidates if candidate in supported)


def opencode_reasoning_effort_client(
    provider: ProviderNode,
    effort: str,
) -> tuple[BamlClient, str]:
    model_id = model_id_for_surface(provider.content.baml_surface)
    if model_id is None:
        msg = f"provider has no OpenCode Go model id: {provider.id}"
        raise ValueError(msg)

    client_name = _client_name(provider.content.baml_surface, effort)
    return compiled_client(client_name), client_name


def unsupported_reasoning_effort_error(error: Exception) -> bool:
    text = str(error).lower()
    return (
        "400" in text
        or "bad request" in text
        or "invalid_request_error" in text
    )


def collector_usage(collector: Collector) -> dict[str, int | None]:
    usage = collector.usage
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cached_input_tokens": usage.cached_input_tokens,
    }


def collector_stop_reason(collector: Collector) -> str | None:
    last = collector.last
    if last is None:
        return None
    value = _get_nested(last, ("stop_reason", "finish_reason"))
    if value is None:
        return None
    return str(value)


def latency_summary(latencies: list[float]) -> dict[str, float | None]:
    return baml_benchmarks.SummariseLatencies(latencies).model_dump(mode="json")


def _client_name(surface: str, effort: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", effort)
    suffix = "".join(part.capitalize() for part in parts if part) or "Default"
    return surface + "Reasoning" + suffix


def _reasoning_efforts_for_surface(surface: str) -> tuple[str, ...] | None:
    for reference in baml_opencode_go.ModelInventory():
        if reference.direct_baml_surface == surface:
            return reference.reasoning_efforts
    return None

def _get_nested(value: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
        if isinstance(value, dict) and name in value:
            return value[name]
    return None
