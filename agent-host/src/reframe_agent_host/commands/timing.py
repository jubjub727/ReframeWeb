from __future__ import annotations

import sys
import time


class TimedEventPrinter:
    def __init__(self) -> None:
        self._started_at = time.perf_counter()
        self._previous_at = self._started_at

    def __call__(self, stage: str, message: str) -> None:
        now = time.perf_counter()
        delta_ms = (now - self._previous_at) * 1000
        total_seconds = now - self._started_at
        self._previous_at = now
        print(
            f"[{stage} +{delta_ms:.0f}ms | {total_seconds:.3f}s] {message}",
            file=sys.stderr,
        )


def print_timing_summary(results) -> None:
    if not results:
        return

    transcription_times = _timing_values(results, "transcription_seconds")
    user_stop_to_transcript_times = _timing_values(
        results,
        "estimated_user_stop_to_transcript_seconds",
    )
    user_stop_to_task_choice_times = _timing_values(
        results,
        "estimated_user_stop_to_task_choice_seconds",
    )
    user_stop_to_memory_search_times = _timing_values(
        results,
        "estimated_user_stop_to_memory_search_seconds",
    )
    user_stop_to_search_depth_times = _timing_values(
        results,
        "estimated_user_stop_to_search_depth_seconds",
    )
    user_stop_to_memory_retrieval_times = _timing_values(
        results,
        "estimated_user_stop_to_memory_retrieval_seconds",
    )
    summary = f"[summary] turns={len(results)}"
    summary += _summary_part("user_stop_to_transcript", user_stop_to_transcript_times)
    summary += _summary_part("transcribe", transcription_times)
    summary += _summary_part("user_stop_to_task_choice", user_stop_to_task_choice_times)
    summary += _summary_part(
        "user_stop_to_memory_search",
        user_stop_to_memory_search_times,
    )
    summary += _summary_part(
        "user_stop_to_search_depth",
        user_stop_to_search_depth_times,
    )
    summary += _summary_part(
        "user_stop_to_memory_retrieval",
        user_stop_to_memory_retrieval_times,
    )
    print(summary, file=sys.stderr)


def _timing_values(results, name: str) -> list[float]:
    return [
        value
        for result in results
        if (value := getattr(result.timings, name)) is not None
    ]


def _summary_part(label: str, values: list[float]) -> str:
    if not values:
        return ""
    return (
        f" {label}_avg={_average(values):.3f}s"
        f" {label}_best={min(values):.3f}s"
        f" {label}_worst={max(values):.3f}s"
    )


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
