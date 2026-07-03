from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ConversationEvaluationCaseAnalysis:
    case_id: str
    request: str
    selected_task_name: str
    review_focus: str
    replies: tuple["ConversationEvaluationReply", ...]


@dataclass(frozen=True)
class ConversationEvaluationReply:
    model_id: str
    provider_name: str
    baml_surface: str
    reasoning_effort: str | None
    run_index: int
    latency_seconds: float
    hints: dict[str, Any] | None
    error: str | None


def conversation_evaluation_case_analyses(
    path: str,
) -> tuple[ConversationEvaluationCaseAnalysis, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = _case_lookup(data)
    replies_by_case = _replies_by_case(data)
    case_ids = list(cases)
    case_ids.extend(
        case_id for case_id in replies_by_case if case_id not in cases
    )

    return tuple(
        ConversationEvaluationCaseAnalysis(
            case_id=case_id,
            request=str(cases.get(case_id, {}).get("current_user_request", "")),
            selected_task_name=str(
                cases.get(case_id, {}).get("selected_task_name", "")
            ),
            review_focus=str(cases.get(case_id, {}).get("review_focus", "")),
            replies=tuple(
                sorted(
                    replies_by_case.get(case_id, ()),
                    key=lambda reply: reply.latency_seconds,
                )
            ),
        )
        for case_id in case_ids
    )


def _case_lookup(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases = {}
    for case in data.get("cases", []):
        if isinstance(case, dict):
            case_id = str(case.get("id", ""))
            if case_id:
                cases[case_id] = case
    return cases


def _replies_by_case(data: dict[str, Any]) -> dict[str, list[ConversationEvaluationReply]]:
    replies_by_case: dict[str, list[ConversationEvaluationReply]] = {}
    for provider in data.get("providers", []):
        if not isinstance(provider, dict):
            continue
        for result in provider.get("case_results", []):
            if not isinstance(result, dict):
                continue
            case_id = str(result.get("case_id", ""))
            if not case_id:
                continue
            replies_by_case.setdefault(case_id, []).append(
                _reply_from_result(provider, result)
            )
    return replies_by_case


def _reply_from_result(
    provider: dict[str, Any],
    result: dict[str, Any],
) -> ConversationEvaluationReply:
    return ConversationEvaluationReply(
        model_id=str(provider.get("model_id") or provider.get("provider_id")),
        provider_name=str(provider.get("provider_name", "")),
        baml_surface=str(provider.get("baml_surface", "")),
        reasoning_effort=_optional_str(
            result.get("reasoning_effort") or provider.get("reasoning_effort")
        ),
        run_index=int(result.get("run_index", 0)),
        latency_seconds=float(result.get("latency_seconds", 0.0)),
        hints=_optional_dict(result.get("hints")),
        error=_optional_str(result.get("error")),
    )


def _optional_dict(value: object) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
