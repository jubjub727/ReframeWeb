from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import time
from typing import Awaitable, Callable

from baml_sdk import task as baml_task
from baml_sdk import voice_turn as baml_voice_turn
from reframe_agent_host.agent_flow.retrieved_memory_graph import retrieved_memory_graph
from reframe_agent_host.voice.capture_types import VoiceTurnControl
from reframe_agent_host.voice.pipeline_config import VoicePipelineEventHandler
from reframe_agent_host.voice.task_flow_state import (
    VoiceTaskAttemptState,
    VoiceTaskCycleState,
)
from reframe_agent_host.voice.turn_side_effects import TurnSideEffects
from reframe_memory.retrieved_context import RetrievedMemoryContext


@dataclass
class VoiceTaskFlowHost:
    current_user_request: str
    turn_flow: object
    side_effects: TurnSideEffects
    post_vad_started_at: float
    on_event: VoicePipelineEventHandler | None
    turn_control: VoiceTurnControl | None
    loop: asyncio.AbstractEventLoop
    cycles: dict[str, VoiceTaskCycleState] = field(default_factory=dict)
    attempts: dict[str, VoiceTaskAttemptState] = field(default_factory=dict)
    _cycle_number: int = 0
    _attempt_number: int = 0

    @property
    def callbacks(self) -> dict[str, Callable]:
        return {
            name: self._sync(getattr(self, name))
            for name in (
                "load_context",
                "retrieve_memories",
                "execute_task",
                "dispatch_task_outputs",
                "summarize_task_actions",
                "record_validation_reply",
            )
        }

    async def load_context(self) -> baml_voice_turn.VoiceTaskFlowContext:
        self._cycle_number += 1
        cycle_id = f"voice-cycle-{self._cycle_number}"
        inputs = await self.turn_flow.voice_turn_inputs(self.current_user_request)
        self.cycles[cycle_id] = VoiceTaskCycleState()
        return baml_voice_turn.VoiceTaskFlowContext(cycle_id=cycle_id, **inputs)

    async def retrieve_memories(self, cycle_id, understanding):
        cycle = self.cycles[cycle_id]
        cycle.post_vad_understanding_seconds = self._post_vad_seconds()
        timings = understanding.timings
        _emit(
            self.on_event,
            "task-chosen",
            f"selected: {understanding.selected_task.name} "
            f"({_seconds(timings.task_choice_ms):.3f}s)",
        )
        _emit(
            self.on_event,
            "memory-search-hints",
            f"{understanding.memory_search_hints.model_dump(mode='json')} "
            f"({_seconds(timings.memory_search_ms):.3f}s)",
        )
        _emit(
            self.on_event,
            "search-depths",
            f"{understanding.search_depths.model_dump(mode='json')} "
            f"({_seconds(timings.search_depth_ms):.3f}s)",
        )
        await self._checkpoint()
        result, seconds, post_seconds = await self.side_effects.retrieve_memories(
            understanding.memory_search_hints,
            understanding.search_depths,
            self.post_vad_started_at,
            self.on_event,
        )
        cycle = self.cycles[cycle_id]
        cycle.retrieved_memories = result
        cycle.memory_retrieval_seconds = seconds
        cycle.post_vad_memory_retrieval_seconds = post_seconds
        await self._checkpoint()
        return retrieved_memory_graph(result or RetrievedMemoryContext())

    async def execute_task(
        self,
        cycle_id,
        task_choice,
        full_prompt,
        continuation,
    ):
        cycle = self.cycles[cycle_id]
        if cycle.post_vad_continuation_seconds is None:
            cycle.post_vad_continuation_seconds = self._post_vad_seconds()
            timings = continuation.timings
            _emit(
                self.on_event,
                "memory-relevance-decision",
                f"{continuation.relevance_decision.model_dump(mode='json')} "
                f"({_seconds(timings.memory_relevance_ms):.3f}s)",
            )
            _emit(
                self.on_event,
                "task-prompt-generated",
                f"{len(full_prompt)} chars "
                f"({_seconds(timings.task_prompt_ms):.3f}s)",
            )
            await self._checkpoint()
        self._attempt_number += 1
        attempt_id = f"task-attempt-{self._attempt_number}"
        prompt = baml_task.TaskPromptDecision(
            full_task_prompt=full_prompt,
            candidate_memory=None,
        )
        execution, execution_s, execution_post_s = await self.side_effects.execute_task(
            task_choice, prompt, self.post_vad_started_at, self.on_event
        )
        await self._checkpoint()
        self.attempts[attempt_id] = VoiceTaskAttemptState(
            task_execution=execution,
            task_execution_seconds=execution_s,
            post_vad_task_execution_seconds=execution_post_s,
        )
        return baml_voice_turn.VoiceTaskExecutionBoundaryResult(
            attempt_id=attempt_id,
            task_execution=execution,
        )

    async def dispatch_task_outputs(self, attempt_id) -> bool:
        attempt = self.attempts[attempt_id]
        dispatch, dispatch_s, dispatch_post_s = await self.side_effects.dispatch_primitives(
            attempt.task_execution, self.post_vad_started_at, self.on_event
        )
        await self._checkpoint()
        attempt.primitive_dispatch = dispatch
        attempt.primitive_dispatch_seconds = dispatch_s
        attempt.post_vad_primitive_dispatch_seconds = dispatch_post_s
        return True

    async def summarize_task_actions(self, attempt_id, task_choice):
        attempt = self.attempts[attempt_id]
        summary, summary_s, summary_post_s = await self.side_effects.summarize_action_history(
            attempt.primitive_dispatch,
            task_choice,
            self.post_vad_started_at,
            self.on_event,
        )
        await self._checkpoint()
        attempt.output_summary = summary
        attempt.output_summary_seconds = summary_s
        attempt.post_vad_output_summary_seconds = summary_post_s
        return summary

    async def record_validation_reply(self, _attempt_id, reply) -> bool:
        await self.side_effects.record_validation_reply(reply, self.on_event)
        await self._checkpoint()
        return True

    def _sync(self, callback: Callable[..., Awaitable]):
        def invoke(*args):
            return asyncio.run_coroutine_threadsafe(callback(*args), self.loop).result()

        return invoke

    async def _checkpoint(self) -> None:
        if self.turn_control is not None:
            await self.turn_control.checkpoint()

    def _post_vad_seconds(self) -> float:
        return time.perf_counter() - self.post_vad_started_at


def _seconds(milliseconds) -> float:
    return float(milliseconds) / 1000.0


def _emit(on_event, stage: str, message: str) -> None:
    if on_event is not None:
        on_event(stage, message)
