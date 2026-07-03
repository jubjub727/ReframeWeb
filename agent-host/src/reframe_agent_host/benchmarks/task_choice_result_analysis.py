from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FailedProviderGroup:
    provider_id: str
    provider_name: str
    model_id: str | None
    baml_surface: str
    reasoning_effort: str | None
    status: str
    case_ids: tuple[str, ...]


def task_choice_failed_provider_groups(path: str) -> tuple[FailedProviderGroup, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    groups = []
    for provider in data.get("providers", []):
        if not isinstance(provider, dict):
            continue
        failed = _failed_case_results(provider)
        if not failed:
            continue
        groups.append(
            FailedProviderGroup(
                provider_id=str(provider.get("provider_id")),
                provider_name=str(provider.get("provider_name")),
                model_id=_optional_str(provider.get("model_id")),
                baml_surface=str(provider.get("baml_surface")),
                reasoning_effort=_optional_str(provider.get("reasoning_effort")),
                status=_status_for_failures(failed),
                case_ids=tuple(str(result.get("case_id")) for result in failed),
            )
        )
    return tuple(groups)


def _failed_case_results(provider: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        result
        for result in provider.get("case_results", [])
        if isinstance(result, dict) and "error" in result
    ]


def _status_for_failures(failures: list[dict[str, Any]]) -> str:
    statuses = {_status_for_error(str(result.get("error", ""))) for result in failures}
    if len(statuses) == 1:
        return next(iter(statuses))
    return "mixed"


def _status_for_error(error: str) -> str:
    lowered = error.lower()
    if "503" in error:
        return "503"
    if "model_not_supported" in lowered or "not supported" in lowered:
        return "unsupported"
    if "500" in error:
        return "500"
    if "400" in error:
        return "400"
    return "other"


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
