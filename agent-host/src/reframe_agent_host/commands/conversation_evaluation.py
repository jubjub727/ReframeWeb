from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from reframe_agent_host.benchmarks import (
    ConversationEvaluationBenchmarkConfig,
    run_conversation_evaluation_benchmark,
)
from reframe_agent_host.benchmarks.conversation_evaluation_result_analysis import (
    ConversationEvaluationCaseAnalysis,
    ConversationEvaluationReply,
    conversation_evaluation_case_analyses,
)
from reframe_memory import open_memory_database


async def run_benchmark_conversation_evaluation(
    runs: int,
    warmup_runs: int,
    delay_seconds: float,
    provider_cooldown_seconds: float,
    provider_ids: list[str] | None,
    case_ids: list[str] | None,
    output: str | None,
) -> int:
    database = await open_memory_database()
    try:
        await database.apply_schema()
        await database.ensure_roots()
        result = await run_conversation_evaluation_benchmark(
            database=database,
            config=ConversationEvaluationBenchmarkConfig(
                runs=runs,
                warmup_runs=warmup_runs,
                delay_seconds=delay_seconds,
                provider_cooldown_seconds=provider_cooldown_seconds,
                provider_ids=tuple(provider_ids or ()),
                case_ids=tuple(case_ids or ()),
            ),
        )
        output_path = _write_benchmark_result(result, output)
        _print_benchmark_saved(output_path, result)
        return 0
    finally:
        await database.close()


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
    if reply.run_index:
        return f"{reply.model_id} r{reply.run_index}"
    return reply.model_id


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


def _write_benchmark_result(result: dict[str, object], output: str | None) -> Path:
    path = Path(output) if output else _default_benchmark_output_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return path.resolve()


def _default_benchmark_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("benchmark-results") / f"conversation-evaluation-{stamp}.json"


def _print_benchmark_saved(path: Path, result: dict[str, object]) -> None:
    summary = result.get("summary")
    print(f"benchmark JSON saved to {path}")
    if isinstance(summary, dict):
        print(
            "summary: "
            f"providers={summary.get('providers')} "
            f"cases={summary.get('cases')} "
            f"total={summary.get('total')} "
            f"errors={summary.get('errors')}"
        )
