from __future__ import annotations

from typing import Any


def print_control_flow_report(result: dict[str, object]) -> None:
    _print_summary(result.get("summary"))
    _print_snapshots(result.get("snapshots"))
    for provider in _dicts(result.get("providers")):
        _print_provider(provider)


def _print_summary(summary: object) -> None:
    if not isinstance(summary, dict):
        return
    print(
        "summary: "
        f"base_providers={summary.get('base_providers', summary.get('providers'))} "
        "provider_effort_runs="
        f"{summary.get('provider_effort_runs', summary.get('providers'))} "
        f"model={summary.get('search_depth_model_id')} "
        f"cases={summary.get('cases')} "
        f"snapshots={summary.get('snapshots')} "
        f"snapshot_errors={summary.get('snapshot_errors')} "
        f"total={summary.get('total')} "
        f"correct={summary.get('correct')} "
        f"errors={summary.get('errors')} "
        f"accuracy={summary.get('accuracy')}"
    )


def _print_snapshots(value: object) -> None:
    snapshots = _dicts(value)
    if not snapshots:
        return

    print()
    print("snapshots:")
    for snapshot in snapshots:
        stages = snapshot.get("stage_latency_seconds")
        stage_text = ""
        if isinstance(stages, dict):
            stage_text = (
                f" task={_latency(stages.get('task_choice'))}"
                f" hints={_latency(stages.get('search_hints'))}"
            )
        if snapshot.get("error"):
            print(
                f"  {snapshot.get('case_id')}: "
                f"ERROR {snapshot.get('error')}{stage_text}"
            )
            continue
        print(
            f"  {snapshot.get('case_id')}: "
            f"total={_latency(snapshot.get('latency_seconds'))}{stage_text} "
            f"selected={snapshot.get('selected_task_id')} "
            f"correct={snapshot.get('task_correct')}"
        )


def _print_provider(provider: dict[str, Any]) -> None:
    label = provider.get("model_id") or provider.get("provider_id")
    if provider.get("reasoning_effort"):
        label = f"{label}/{provider.get('reasoning_effort')}"
    print()
    print(
        f"{label} "
        f"avg={_latency(_summary_value(provider, 'latency_seconds', 'average'))} "
        f"best={_latency(_summary_value(provider, 'latency_seconds', 'best'))} "
        f"worst={_latency(_summary_value(provider, 'latency_seconds', 'worst'))}"
    )
    stages = provider.get("stage_latency_seconds")
    if isinstance(stages, dict):
        print(
            "  stages: "
            f"depth={_latency(_summary_value(stages, 'search_depth', 'average'))}"
        )
    for result in _dicts(provider.get("case_results")):
        _print_case_result(result)


def _print_case_result(result: dict[str, Any]) -> None:
    if result.get("error"):
        print(
            f"  {result.get('case_id')} r{result.get('run_index')}: "
            f"ERROR {result['error']}"
        )
        return

    stages = result.get("stage_latency_seconds")
    stage_text = ""
    if isinstance(stages, dict):
        stage_text = (
            f" depth={_latency(stages.get('search_depth'))}"
        )
    print(
        f"  {result.get('case_id')} r{result.get('run_index')}: "
        f"total={_latency(result.get('latency_seconds'))}{stage_text} "
        f"selected={result.get('selected_task_id')} "
        f"correct={result.get('task_correct')}"
    )
    for domain, fields in _dicts_by_key(result.get("search_depth_ages")):
        pieces = [
            f"{field.replace('_after', '')}={age.get('display')}"
            for field, age in _dicts_by_key(fields)
        ]
        print(f"    {domain}: " + ", ".join(pieces))


def _summary_value(data: dict[str, Any], key: str, subkey: str) -> object:
    value = data.get(key)
    if not isinstance(value, dict):
        return None
    return value.get(subkey)


def _latency(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    if value < 1:
        return f"{value * 1000:.1f} ms"
    return f"{value:.3f} s"


def _dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dicts_by_key(value: object) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(value, dict):
        return []
    return [
        (str(key), item)
        for key, item in value.items()
        if isinstance(item, dict)
    ]
