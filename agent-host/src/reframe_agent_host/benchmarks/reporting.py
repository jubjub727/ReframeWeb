from __future__ import annotations

from reframe_agent_host.benchmarks.reasoning_efforts import latency_summary


def benchmark_summary(results, items, providers, config, live_latency=False):
    total = sum(int(result["total"]) for result in results)
    correct = sum(int(result.get("correct", 0)) for result in results)
    errors = sum(int(result["errors"]) for result in results)
    summary = {
        "base_providers": len(providers),
        "provider_effort_runs": len(results),
        "providers": len(results),
        "cases": len(items),
        "reasoning_effort_candidates": list(config.reasoning_effort_candidates),
        "configured_reasoning_efforts": list(config.reasoning_efforts),
        "runs_per_case": config.runs,
        "total": total,
        "correct": correct,
        "errors": errors,
        "accuracy": correct / total if total else 0.0,
        "delay_seconds": config.delay_seconds,
        "provider_cooldown_seconds": config.provider_cooldown_seconds,
    }
    if items and hasattr(items[0], "latency_seconds"):
        snapshot_correct = sum(bool(item.task_correct) for item in items)
        summary.update(
            snapshots=len(items),
            snapshot_errors=sum(item.error is not None for item in items),
            snapshot_task_correct=snapshot_correct,
            snapshot_accuracy=snapshot_correct / len(items),
            snapshot_latency_seconds=latency_summary(
                [item.latency_seconds for item in items]
            ),
        )
    if live_latency:
        latencies = [
            case["latency_seconds"]
            for result in results
            for case in result.get("case_results", [])
            if isinstance(case, dict) and "latency_seconds" in case
        ]
        summary["latency_seconds"] = latency_summary(latencies)
    return summary


def control_flow_case_summary(case):
    return {
        "id": case.id,
        "current_timestamp": case.current_timestamp,
        "current_user_request": case.current_user_request,
        "expected_task_id": case.expected_task_id,
        "available_tasks": len(case.available_tasks),
        "session": {
            "id": case.session.id,
            "name": case.session.name,
            "created_at": case.session.created_at,
            "updated_at": case.session.updated_at,
            "read_at": case.session.read_at,
            "conversations": len(case.session.conversations),
            "memories": len(case.session.memories),
        },
        "task_choice_memories": len(case.task_choice_memories),
        "conversation_evaluation_memories": len(
            case.conversation_evaluation_memories
        ),
        "search_depth_memories": len(case.search_depth_memories),
    }


def memory_relevance_case_summary(case):
    return {
        "id": case.id,
        "current_timestamp": case.current_timestamp,
        "current_user_request": case.current_user_request,
        "expected_task_id": case.expected_task_id,
        "session": {
            "id": case.session.id,
            "name": case.session.name,
            "conversations": len(case.session.conversations),
            "memories": len(case.session.memories),
        },
    }


def task_prompt_case_summary(case):
    return {
        "id": case.id,
        "current_user_request": case.current_user_request,
        "expected_task_name": case.expected_task_name,
        "conversation_name": case.conversation_name,
        "messages": len(case.messages),
        "session_memories": len(case.session_memories),
    }


def conversation_case_summary(case):
    return {
        "id": case.id,
        "current_user_request": case.current_user_request,
        "selected_task_name": case.selected_task.name,
        "session_conversations": len(case.session_conversations),
        "session_memories": len(case.session_memories),
        "conversation_evaluation_memories": len(
            case.conversation_evaluation_memories
        ),
        "review_focus": case.review_focus,
    }
