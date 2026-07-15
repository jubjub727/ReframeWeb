from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
from threading import Thread

from baml_sdk import memory as baml_memory
from baml_sdk import task_catalog as baml_task_catalog
from baml_sdk import task as baml_task

from reframe_agent_host.agent_flow.action_history import ActionHistorySummarizer
from reframe_agent_host.agent_flow.live_conversation import LiveConversationContext
from reframe_agent_host.agent_flow.task_completion import TaskCompletionChecker
from reframe_agent_host.agent_flow.task_execution import TaskExecutionPlanner
from reframe_agent_host.speech.tts import TextSpeaker
from reframe_agent_host.task_execution import PrimitiveDispatcher
from reframe_agent_host.voice.conversation_mode import ConversationModeController
from reframe_agent_host.voice.pipeline_config import (
    VoicePipelineConfig,
    VoicePipelineEventHandler,
)
from reframe_memory import ConversationMessage, RetrievedMemoryContext, open_memory_database


@dataclass
class TurnSideEffects:
    config: VoicePipelineConfig
    memory_retrieval: object
    task_execution: TaskExecutionPlanner | None
    speaker: TextSpeaker
    mode_controller: ConversationModeController | None
    turn_flow: object | None
    live_conversation: LiveConversationContext | None

    async def close(self) -> None:
        for component in (
            self.memory_retrieval,
            self.task_execution,
            self.turn_flow,
        ):
            close = getattr(component, "close", None)
            if close is not None:
                await close()

    def remember_live_human_reply(self, transcript: str) -> str | None:
        if self.live_conversation is not None:
            return self.live_conversation.add_message(
                self.config.conversation_id,
                role="human",
                content=transcript,
            )
        return None

    def resolve_live_human_reply(self, captured_at: str | None) -> None:
        if self.live_conversation is not None:
            self.live_conversation.resolve_human_reply(captured_at)

    def record_human_reply_in_background(
        self,
        transcript: str,
        on_event: VoicePipelineEventHandler | None,
    ) -> None:
        if self.config.conversation_id is None or not transcript:
            return

        def record() -> None:
            try:
                asyncio.run(self._record_human_reply(transcript, on_event))
            except Exception as error:
                _emit(on_event, "warning", f"failed to record human reply: {error}")

        Thread(target=record, daemon=True).start()

    async def retrieve_memories(
        self,
        hints: baml_memory.ConversationMemorySearchHints | None,
        depths: baml_memory.SearchDepthDecision | None,
        post_vad_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ) -> tuple[RetrievedMemoryContext | None, float | None, float | None]:
        if hints is None or depths is None:
            return None, None, None
        _emit(on_event, "memory-retrieval", "retrieving graph memory context")
        started_at = time.perf_counter()
        result = await self.memory_retrieval.retrieve(
            memory_search_hints=hints,
            search_depths=depths,
        )
        seconds = time.perf_counter() - started_at
        _emit(on_event, "memory-retrieved", f"{result.to_dict()} ({seconds:.3f}s)")
        return result, seconds, time.perf_counter() - post_vad_started_at

    async def execute_task(
        self,
        task_choice: baml_task.TaskChoiceDecision | None,
        task_prompt: baml_task.TaskPromptDecision | None,
        post_vad_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ) -> tuple[baml_task.TaskExecutionResult | None, float | None, float | None]:
        if self.task_execution is None or task_choice is None or task_prompt is None:
            return None, None, None
        _emit(on_event, "task-execution", "executing selected task")
        started_at = time.perf_counter()
        result = await self.task_execution.execute_task(
            selected_task_id=task_choice.selected_task_id,
            full_task_prompt=task_prompt.full_task_prompt,
            prompt_layer_debug=self.prompt_layer_debug,
        )
        seconds = time.perf_counter() - started_at
        _emit(
            on_event,
            "task-executed",
            f"{len(result.returns)} return items ({seconds:.3f}s)",
        )
        return result, seconds, time.perf_counter() - post_vad_started_at

    async def dispatch_primitives(
        self,
        execution: baml_task.TaskExecutionResult | None,
        post_vad_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ):
        if execution is None or not execution.returns:
            return None, None, None
        _emit(on_event, "primitive-dispatch", "handling task return items")
        started_at = time.perf_counter()
        database = await open_memory_database()
        try:
            result = await PrimitiveDispatcher(
                database=database,
                session_id=self.config.session_id,
                conversation_id=self.config.conversation_id,
                speaker=self.speaker,
                on_event=on_event,
                on_conversation_mode_off=(
                    self.mode_controller.turn_off_conversation
                    if self.mode_controller is not None
                    else None
                ),
            ).dispatch(execution)
        finally:
            await database.close()
        seconds = time.perf_counter() - started_at
        _emit(
            on_event,
            "primitive-dispatched",
            f"{len(result.records)} items ({seconds:.3f}s)",
        )
        return result, seconds, time.perf_counter() - post_vad_started_at

    async def summarize_action_history(
        self,
        dispatch,
        task_choice: baml_task.TaskChoiceDecision | None,
        post_vad_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ):
        if dispatch is None or dispatch.task_history_id is None:
            return None, None, None
        _emit(on_event, "action-history-summary", "summarizing recorded action history")
        started_at = time.perf_counter()
        summarizer = ActionHistorySummarizer()
        try:
            result = await summarizer.summarize(
                dispatch.task_history_id,
                selected_task_id=(
                    task_choice.selected_task_id if task_choice is not None else None
                ),
                prompt_layer_debug=self.prompt_layer_debug,
            )
        finally:
            await summarizer.close()
        seconds = time.perf_counter() - started_at
        _emit(on_event, "action-history-summarized", f"{len(result)} chars ({seconds:.3f}s)")
        return result, seconds, time.perf_counter() - post_vad_started_at

    async def record_validation_reply(
        self,
        reply: str | None,
        on_event: VoicePipelineEventHandler | None,
    ) -> None:
        clean = " ".join((reply or "").split())
        if not clean:
            return
        if self.live_conversation is not None:
            self.live_conversation.add_message(
                self.config.conversation_id,
                role="validation_reply",
                content=clean,
            )
        if self.config.conversation_id is not None:
            database = await open_memory_database()
            try:
                await database.conversations.add_message(
                    self.config.conversation_id,
                    ConversationMessage(role="validation_reply", content=clean),
                )
            finally:
                await database.close()
        _emit(on_event, "validation-reply", clean)

    async def check_task_completion(
        self,
        selected_task: baml_task_catalog.SelectedTaskContext | None,
        action_history_summary: str | None,
        post_vad_started_at: float,
        on_event: VoicePipelineEventHandler | None,
    ) -> tuple[baml_task.CompletionResult | None, float | None, float | None]:
        if selected_task is None or action_history_summary is None:
            return None, None, None
        _emit(on_event, "task-completion-review", "checking task completion")
        started_at = time.perf_counter()
        result = await TaskCompletionChecker().check(
            completion_string=selected_task.output,
            output_summary=action_history_summary,
            prompt_layer_debug=self.prompt_layer_debug,
        )
        seconds = time.perf_counter() - started_at
        _emit(on_event, "task-completion-reviewed", f"{result.value} ({seconds:.3f}s)")
        return result, seconds, time.perf_counter() - post_vad_started_at

    @property
    def prompt_layer_debug(self):
        return getattr(self.turn_flow, "prompt_layer_debug", None)

    async def _record_human_reply(self, transcript, on_event) -> None:
        database = await open_memory_database()
        try:
            await database.conversations.add_message(
                self.config.conversation_id,
                ConversationMessage(role="human", content=transcript),
            )
        finally:
            await database.close()
        _emit(
            on_event,
            "conversation-context",
            f"recorded current turn in {self.config.conversation_id}",
        )


def _emit(on_event, stage: str, message: str) -> None:
    if on_event is not None:
        on_event(stage, message)
