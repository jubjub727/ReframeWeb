from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Mapping

from baml_sdk import task_catalog as baml_task_catalog
from baml_sdk import voice_turn as baml_voice_turn
from reframe_agent_host.agent_flow.live_conversation import LiveConversationContext
from reframe_agent_host.agent_flow.machine_state import MachineStateProvider
from reframe_agent_host.agent_flow.prompt_layer_debug import PromptLayerDebugSession
from reframe_agent_host.agent_flow.provider_clients import client_kwargs
from reframe_agent_host.agent_flow.voice_prompt_debug import (
    dump_continuation_layers,
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
