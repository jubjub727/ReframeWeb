from __future__ import annotations

import time


def print_turn_completed(total_seconds: float) -> None:
    print(f"[completed in {total_seconds:.3f}s]", flush=True)


class VoiceTurnEventPrinter:
    _DISPLAY_NAMES = {
        "primitive-dispatch": "response-items",
        "primitive-dispatched": "response-items",
        "action-history-summary": "action-history-summary",
        "action-history-summarized": "action-history-summary",
        "task-completion-review": "task-completion",
        "task-completion-reviewed": "task-completion",
    }
    _LATENCY_STAGES = {
        "task-chosen": "task_choice",
        "memory-search-hints": "memory_search",
        "search-depths": "search_depth",
        "memory-relevance-decision": "memory_relevance",
        "task-prompt-generated": "task_prompt",
        "task-executed": "task_execution",
        "action-history-summarized": "action_history_summary",
        "task-completion-reviewed": "task_review",
    }
    _DEBUG_STAGES = {
        "preparing",
        "ready",
        "machine-state",
        "listening",
        "audio",
        "transcribing",
        "transcript",
        "human-reply",
        "trigger",
        "keyphrase",
        "speech",
        "task-choice",
        "task-chosen",
        "memory-search",
        "memory-search-hints",
        "search-depth",
        "search-depths",
        "memory-retrieval",
        "memory-relevance",
        "memory-relevance-decision",
        "task-prompt",
        "task-prompt-generated",
        "candidate-memory",
        "task-execution",
        "task-executed",
        "primitive-dispatch",
        "primitive-dispatched",
        "action-history-summary",
        "action-history-summarized",
        "task-completion-review",
        "task-completion-reviewed",
        "validation-reply",
        "task-refinement",
        "task-reselection",
        "task-failure-reply",
        "task-failure-resolved",
        "turn-understanding",
        "turn-continuation",
        "agent-reply",
        "agent-reply-interrupted",
        "agent-thought",
        "conversation-mode",
        "barge-in",
        "tts-error",
        "startup-error",
        "turn-error",
        "turn-ignored",
        "capture-error",
        "warning",
        "conversation-context",
        "debug-audio",
    }

    def __init__(self, *, debug_output: bool, turn_started_at: float) -> None:
        self._debug_output = debug_output
        self._turn_started_at = turn_started_at
        self._startup_reported = False
        self._last_conversation_mode_line: str | None = None

    def __call__(self, stage: str, message: str) -> None:
        if stage == "input-started":
            self._print_live("[Input Started]")
            return
        if stage == "input-stopped":
            self._print_live("[Input Stopped]")
            return
        if stage == "candidate-memory":
            self._print_live(f"candidate_memory: {single_line(message)}")
            return
        if self._debug_output:
            if stage in self._DEBUG_STAGES:
                label = self._DISPLAY_NAMES.get(stage, stage)
                self._print_live(f"[{label}] {message}")
            return
        self._print_normal(stage, message)

    def _print_normal(self, stage: str, message: str) -> None:
        if stage == "listening":
            if self._startup_reported:
                self._print_live("[ready]")
            else:
                self._startup_reported = True
                elapsed = latency(time.perf_counter() - self._turn_started_at)
                self._print_live(f"[startup {elapsed}] ready")
        elif stage in {
            "human-reply",
            "agent-thought",
            "agent-reply",
            "validation-reply",
        }:
            self._print_live(f"{stage.replace('-', '_')}: {single_line(message)}")
        elif stage == "agent-reply-interrupted":
            detail = single_line(message)
            suffix = f": {detail}" if detail else ""
            self._print_live(f"agent_reply_interrupted{suffix}")
        elif stage == "conversation-mode":
            line = _conversation_mode_status_line(message)
            if line != self._last_conversation_mode_line:
                self._last_conversation_mode_line = line
                self._print_live(line)
        elif stage in {"turn-error", "capture-error", "warning", "tts-error"}:
            self._print_live(f"[{stage}] {single_line(message)}")
        elif stage == "startup-error":
            self._print_live(f"[startup-error] {single_line(message)}")
        elif stage == "barge-in":
            self._print_live(f"[barge-in] {single_line(message)}")
        elif stage == "turn-ignored":
            self._print_live(f"[ignored] {single_line(message)}")
        elif stage == "task-chosen":
            selected = _selected_task_from_event(message)
            if selected:
                self._print_live(f"selected: {selected}")
            self._print_event_latency(stage, message)
        elif stage in self._LATENCY_STAGES:
            self._print_event_latency(stage, message)

    def _print_event_latency(self, stage: str, message: str) -> None:
        elapsed = _event_latency(message)
        if elapsed is not None:
            self._print_live(f"[{self._LATENCY_STAGES[stage]} {elapsed}]")

    def _print_live(self, message: str) -> None:
        print(message, flush=True)


def single_line(value: str, limit: int | None = None) -> str:
    text = " ".join(value.split())
    if limit is None or len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def latency(value: float | None) -> str:
    if value is None:
        return "n/a"
    if value < 1:
        return f"{value * 1000:.0f}ms"
    return f"{value:.3f}s"


def _conversation_mode_status_line(message: str) -> str:
    normalized = single_line(message).lower().replace("_", " ").strip()
    if normalized in {
        "continuous conversation",
        "continuous conversation on",
        "conversation on",
        "on",
    }:
        return "[conversation mode] On"
    if normalized in {
        "wake command",
        "continuous conversation off",
        "conversation off",
        "off",
    }:
        return "[conversation mode] Off"
    return f"[conversation mode] {single_line(message)}"


def _event_latency(message: str) -> str | None:
    marker = message.rsplit("(", 1)
    if len(marker) != 2:
        return None
    value = marker[1].rstrip(")").strip()
    if not value.endswith("s"):
        return None
    try:
        return latency(float(value[:-1]))
    except ValueError:
        return None


def _selected_task_from_event(message: str) -> str:
    text = message.strip()
    if not text.lower().startswith("selected:"):
        return ""
    selected = text[len("selected:") :].strip()
    latency_index = selected.rfind("(")
    if latency_index >= 0 and selected.endswith(")"):
        selected = selected[:latency_index].strip()
    return selected
