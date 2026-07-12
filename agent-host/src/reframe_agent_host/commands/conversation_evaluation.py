from __future__ import annotations

from pathlib import Path

from reframe_agent_host.benchmarks.config import ConversationEvaluationBenchmarkConfig
from reframe_agent_host.benchmarks.runner import run_conversation_evaluation_benchmark
from reframe_agent_host.benchmarks.conversation_evaluation_result_analysis import (
    ConversationEvaluationCaseAnalysis,
    ConversationEvaluationReply,
    conversation_evaluation_case_analyses,
)
from reframe_agent_host.commands.benchmarking import (
    benchmark_config_values,
    execute_benchmark,
    print_benchmark_summary,
)


async def run_benchmark_conversation_evaluation(
    runs: int,
    warmup_runs: int,
    delay_seconds: float,
    provider_cooldown_seconds: float,
    provider_ids: list[str] | None,
    case_ids: list[str] | None,
    reasoning_efforts: list[str] | None,
    reasoning_effort_candidates: list[str] | None,
    output: str | None,
) -> int:
    values = benchmark_config_values(
        runs=runs,
        warmup_runs=warmup_runs,
        delay_seconds=delay_seconds,
        provider_cooldown_seconds=provider_cooldown_seconds,
        provider_ids=provider_ids,
        case_ids=case_ids,
        reasoning_efforts=reasoning_efforts,
        reasoning_effort_candidates=reasoning_effort_candidates,
    )
    return await execute_benchmark(
        config=ConversationEvaluationBenchmarkConfig(**values),
        runner=run_conversation_evaluation_benchmark,
        output=output,
        output_name="conversation-evaluation",
        reporter=_print_benchmark_saved,
    )


def run_analyze_conversation_evaluation_benchmark(path: str) -> int:
    analyses = conversation_evaluation_case_analyses(path)
    if not analyses:
        print("no benchmark cases found")
        return 0

    for index, analysis in enumerate(analyses):
        if index > 0:
            print()
        _print_case_analysis(analysis)
    return 0


def _print_case_analysis(analysis: ConversationEvaluationCaseAnalysis) -> None:
    print(f"Case: {analysis.case_id}")
    if analysis.request:
        print(f"Request: {analysis.request}")
    if analysis.selected_task_name:
        print(f"Selected task: {analysis.selected_task_name}")
    if analysis.review_focus:
        print(f"Review focus: {analysis.review_focus}")

    if not analysis.replies:
        print("Replies: []")
        return

    print("Replies by latency:")
    _print_reply_table(analysis.replies)


def _print_reply_table(replies: tuple[ConversationEvaluationReply, ...]) -> None:
    headers = (
        "#",
        "latency",
        "model",
        "tags",
        "contains",
        "equals",
        "candidate_memory",
        "error",
    )
    rows = [
        (
            str(rank),
            _format_latency(reply.latency_seconds),
            _reply_label(reply),
            _tag_summary(reply),
            _string_summary(reply, "contains"),
            _string_summary(reply, "equals"),
            _candidate_summary(reply),
            _error_summary(reply),
        )
        for rank, reply in enumerate(replies, start=1)
    ]
    widths = _column_widths(headers, rows)
    print(_table_row(headers, widths))
    print(_table_rule(widths))
    for row in rows:
        print(_table_row(row, widths))


def _reply_label(reply: ConversationEvaluationReply) -> str:
    effort = f"/{reply.reasoning_effort}" if reply.reasoning_effort else ""
    if reply.run_index:
        return f"{reply.model_id}{effort} r{reply.run_index}"
    return f"{reply.model_id}{effort}"


def _tag_summary(reply: ConversationEvaluationReply) -> str:
    tags = (reply.hints or {}).get("tags")
    if not isinstance(tags, dict):
        return ""
    pieces = []
    for key, label in (
        ("any_of", "any"),
        ("all_of", "all"),
        ("none_of", "none"),
    ):
        values = _string_list(tags.get(key))
        if values:
            pieces.append(f"{label}={', '.join(values)}")
    return "; ".join(pieces)


def _string_summary(reply: ConversationEvaluationReply, key: str) -> str:
    strings = (reply.hints or {}).get("strings")
    if not isinstance(strings, dict):
        return ""
    return ", ".join(_string_list(strings.get(key)))


def _error_summary(reply: ConversationEvaluationReply) -> str:
    if reply.error is None:
        return ""
    return " ".join(reply.error.split())


def _candidate_summary(reply: ConversationEvaluationReply) -> str:
    candidate = (reply.hints or {}).get("candidate_memory")
    if not isinstance(candidate, dict):
        return ""
    title = str(candidate.get("title") or "").strip()
    description = str(candidate.get("description") or "").strip()
    if title and description:
        return f"{title}: {description}"
    return title or description


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _column_widths(
    headers: tuple[str, ...],
    rows: list[tuple[str, ...]],
) -> tuple[int, ...]:
    widths = []
    for index, header in enumerate(headers):
        widths.append(
            max(
                [len(header)]
                + [len(row[index]) for row in rows],
            )
        )
    return tuple(widths)


def _table_row(row: tuple[str, ...], widths: tuple[int, ...]) -> str:
    cells = [
        value.ljust(width)
        for value, width in zip(row, widths)
    ]
    return " | ".join(cells)


def _table_rule(widths: tuple[int, ...]) -> str:
    return "-+-".join("-" * width for width in widths)


def _format_latency(seconds: float) -> str:
    return f"{seconds * 1000:.1f} ms"


def _print_benchmark_saved(path: Path, result: dict[str, object]) -> None:
    print_benchmark_summary(path, result, _SUMMARY_FIELDS)


_SUMMARY_FIELDS = (
    ("base_providers", "base_providers"),
    ("provider_effort_runs", "provider_effort_runs"),
    ("model", "conversation_evaluation_model_id"),
    ("cases", "cases"),
    ("total", "total"),
    ("errors", "errors"),
)
