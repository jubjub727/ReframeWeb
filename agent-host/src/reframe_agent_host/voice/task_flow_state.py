from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VoiceTaskCycleState:
    context_inputs: object | None = None
    understanding: object | None = None
    retrieved_memories: object | None = None
    retrieved_memory_graph: object | None = None
    post_vad_understanding_seconds: float | None = None
    memory_retrieval_seconds: float | None = None
    post_vad_memory_retrieval_seconds: float | None = None
    post_vad_continuation_seconds: float | None = None


@dataclass
class VoiceTaskAttemptState:
    task_execution: object | None = None
    task_execution_seconds: float | None = None
    post_vad_task_execution_seconds: float | None = None
    primitive_dispatch: object | None = None
    primitive_dispatch_seconds: float | None = None
    post_vad_primitive_dispatch_seconds: float | None = None
    output_summary: str | None = None
    output_summary_seconds: float | None = None
    post_vad_output_summary_seconds: float | None = None
    post_vad_task_completion_seconds: float | None = None
