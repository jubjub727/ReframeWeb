from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Mapping

from baml_sdk import task_catalog as baml_task_catalog
from baml_sdk import voice_turn as baml_voice_turn
from reframe_agent_host.agent_flow.candidate_memory_writeback import (
    write_candidate_memories,
)
from reframe_agent_host.agent_flow.live_conversation import LiveConversationContext
from reframe_agent_host.agent_flow.machine_state import MachineStateProvider
from reframe_agent_host.agent_flow.prompt_layer_debug import PromptLayerDebugSession
from reframe_agent_host.agent_flow.provider_clients import client_kwargs
from reframe_agent_host.agent_flow.task_review_debug import dump_task_reviews
from reframe_agent_host.agent_flow.voice_turn_debug import (
    record_continuation_layers,
    record_understanding_layers,
)
from reframe_agent_host.agent_flow.voice_prompt_debug import (
    dump_continuation_layers,
    dump_task_choice_layer,
    dump_understanding_layers,
)
from reframe_agent_host.agent_flow.voice_turn_context import VoiceTurnContext
from reframe_memory import MemoryDatabase
from reframe_memory.retrieved_context import RetrievedMemoryContext


@dataclass
class BamlVoiceTurnFlow:
    database: MemoryDatabase | None = None
    session_id: str | None = None
    conversation_id: str | None = None
    client_name: str | None = None
    machine_state_provider: MachineStateProvider | None = None
    live_conversation: LiveConversationContext | None = None
    _prompt_debug: PromptLayerDebugSession | None = field(init=False, default=None)
    _context: VoiceTurnContext = field(init=False)

    def __post_init__(self) -> None:
        self._context = VoiceTurnContext(
            database=self.database,
            session_id=self.session_id,
            conversation_id=self.conversation_id,
            machine_state_provider=self.machine_state_provider,
            live_conversation=self.live_conversation,
        )

    @property
    def prompt_layer_debug(self) -> PromptLayerDebugSession | None:
        return self._prompt_debug

    async def understand_prompt(
        self,
        current_user_request: str,
    ) -> baml_voice_turn.VoicePromptUnderstanding:
        inputs = await self._context.understanding_inputs(current_user_request)
        self._prompt_debug = PromptLayerDebugSession.begin(
            current_user_request=current_user_request,
        )
        kwargs = client_kwargs(self.client_name)
        result = await self._run_understanding(inputs, kwargs)
        try:
            await dump_understanding_layers(self._prompt_debug, inputs, result, kwargs)
        except Exception:
            pass
        return result

    async def continue_prompt(
        self,
        current_user_request: str,
        selected_task: baml_task_catalog.SelectedTaskContext,
        retrieved_memories: RetrievedMemoryContext,
    ) -> baml_voice_turn.VoicePromptContinuation:
        inputs = await self._context.continuation_inputs(
            current_user_request,
            selected_task,
            retrieved_memories,
        )
        if self._prompt_debug is None:
            self._prompt_debug = PromptLayerDebugSession.begin(
                current_user_request=current_user_request,
            )
        kwargs = client_kwargs(self.client_name)
        result = await self._run_continuation(inputs, kwargs)
        try:
            await dump_continuation_layers(self._prompt_debug, inputs, result, kwargs)
        except Exception:
            pass
        return result

    async def voice_turn_inputs(self, current_user_request: str) -> dict:
        if self._prompt_debug is None:
            self._prompt_debug = PromptLayerDebugSession.begin(
                current_user_request=current_user_request,
            )
        return await self._context.voice_turn_inputs(current_user_request)

    def bind_human_reply(self, created_at: str | None) -> None:
        self._context.current_human_reply_created_at = created_at

    def task_conversation_scope(self) -> dict:
        return self._context.task_conversation_scope()

    async def current_conversation(self):
        return await self._context.current_conversation()

    async def write_candidate_memories(self, batch) -> None:
        await write_candidate_memories(
            await self._context.memory_database(),
            batch,
        )

    async def record_task_choice(self, inputs, task_choice, task_choice_ms) -> None:
        if self._prompt_debug is not None:
            try:
                await dump_task_choice_layer(
                    self._prompt_debug,
                    inputs,
                    task_choice,
                    task_choice_ms,
                    client_kwargs(self.client_name),
                )
            except Exception:
                pass

    async def run_voice_turn(self, current_user_request: str, host):
        try:
            result = await baml_voice_turn.RunVoiceTurn_async(
                current_user_request=current_user_request,
                **host.callbacks,
                **client_kwargs(self.client_name),
            )
        except Exception as error:
            self._write_debug_layer(
                99,
                "run_voice_turn",
                inputs={"current_user_request": current_user_request},
                error=error,
            )
            raise
        if (
            self._prompt_debug is not None
            and isinstance(result, baml_voice_turn.VoiceTaskFlowResult)
        ):
            try:
                await dump_task_reviews(self._prompt_debug, result)
            except Exception:
                pass
        return result

    async def record_understanding(self, inputs, result) -> None:
        if self._prompt_debug is not None:
            try:
                await record_understanding_layers(
                    self._prompt_debug,
                    inputs,
                    result,
                    client_kwargs(self.client_name),
                )
            except Exception:
                pass

    async def record_continuation(
        self,
        context_inputs,
        selected_task,
        retrieved_memories,
        result,
    ) -> None:
        if self._prompt_debug is not None:
            try:
                await record_continuation_layers(
                    self._prompt_debug,
                    context_inputs,
                    selected_task,
                    retrieved_memories,
                    result,
                    client_kwargs(self.client_name),
                )
            except Exception:
                pass

    async def _run_understanding(
        self,
        inputs: Mapping[str, Any],
        kwargs: dict[str, Any],
    ) -> baml_voice_turn.VoicePromptUnderstanding:
        started_at = time.perf_counter()
        try:
            result = await baml_voice_turn.UnderstandVoicePrompt_async(
                **inputs, **kwargs
            )
        except Exception as error:
            self._write_debug_layer(
                0,
                "understand_voice_prompt",
                inputs=inputs,
                elapsed_seconds=time.perf_counter() - started_at,
                error=error,
            )
            raise
        self._write_debug_layer(
            0,
            "understand_voice_prompt",
            inputs=inputs,
            result=result,
            elapsed_seconds=time.perf_counter() - started_at,
        )
        return result

    async def _run_continuation(
        self,
        inputs: Mapping[str, Any],
        kwargs: dict[str, Any],
    ) -> baml_voice_turn.VoicePromptContinuation:
        started_at = time.perf_counter()
        try:
            result = await baml_voice_turn.ContinueVoicePrompt_async(
                **inputs, **kwargs
            )
        except Exception as error:
            self._write_debug_layer(
                4,
                "continue_voice_prompt",
                inputs=inputs,
                elapsed_seconds=time.perf_counter() - started_at,
                error=error,
            )
            raise
        self._write_debug_layer(
            4,
            "continue_voice_prompt",
            inputs=inputs,
            result=result,
            elapsed_seconds=time.perf_counter() - started_at,
        )
        return result

    def _write_debug_layer(
        self,
        order: int,
        name: str,
        *,
        inputs: Mapping[str, Any],
        result: Any = None,
        elapsed_seconds: float | None = None,
        error: Exception | None = None,
    ) -> None:
        if self._prompt_debug is not None:
            self._prompt_debug.write_layer(
                order=order,
                name=name,
                inputs=inputs,
                result=result,
                elapsed_seconds=elapsed_seconds,
                error=error,
            )

    async def task_name(self, task_id: str) -> str | None:
        return await self._context.task_name(task_id)

    async def close(self) -> None:
        await self._context.close()
        self.database = self._context.database
