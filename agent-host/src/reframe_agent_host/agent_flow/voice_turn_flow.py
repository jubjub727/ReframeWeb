from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Awaitable, Callable, Mapping

import baml_sdk as baml
import baml_sdk as types
from reframe_agent_host.agent_flow.baml_clients import client_kwargs
from reframe_agent_host.agent_flow.prompt_layer_debug import (
    PromptLayerDebugSession,
)
from reframe_agent_host.agent_flow.retrieved_memory_graph import (
    retrieved_memory_graph,
)
from reframe_agent_host.agent_flow.search_depth import current_timestamp
from reframe_agent_host.agent_flow.session_context import (
    current_conversation_history,
    session_memory_contexts,
)
from reframe_agent_host.agent_flow.timestamps import timestamp_fields
from reframe_memory import MemoryDatabase, open_memory_database
from reframe_memory.retrieved_context import RetrievedMemoryContext


@dataclass
class BamlVoiceTurnFlow:
    database: MemoryDatabase | None = None
    session_id: str | None = None
    conversation_id: str | None = None
    client_name: str | None = None
    _owns_database: bool = field(init=False)
    _prompt_debug: PromptLayerDebugSession | None = field(
        init=False,
        default=None,
    )

    def __post_init__(self) -> None:
        self._owns_database = self.database is None

    @property
    def prompt_layer_debug(self) -> PromptLayerDebugSession | None:
        return self._prompt_debug

    async def understand_prompt(
        self,
        current_user_request: str,
    ) -> types.VoicePromptUnderstanding:
        database = await self._get_database()
        timestamp = current_timestamp()
        conversation = await current_conversation_history(
            database,
            self.session_id,
            self.conversation_id,
        )
        session_memories = await session_memory_contexts(
            database,
            self.session_id,
        )
        available_tasks = await self._available_tasks(database)
        task_choice_memories = await self._task_choice_memories(database)
        conversation_evaluation_memories = (
            await self._conversation_evaluation_memories(database)
        )
        search_depth_memories = await self._search_depth_memories(database)
        inputs = {
            "current_timestamp": timestamp,
            "current_user_request": current_user_request,
            "current_conversation": conversation,
            "session_memories": session_memories,
            "available_tasks": available_tasks,
            "task_choice_memories": task_choice_memories,
            "conversation_evaluation_memories": conversation_evaluation_memories,
            "search_depth_memories": search_depth_memories,
        }
        self._prompt_debug = PromptLayerDebugSession.begin(
            current_user_request=current_user_request,
        )
        kwargs = client_kwargs(self.client_name)
        started_at = time.perf_counter()
        try:
            result = await baml.UnderstandVoicePrompt_async(
                **inputs,
                **kwargs,
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
        try:
            await self._dump_understanding_prompt_layers(inputs, result, kwargs)
        except Exception:
            pass
        return result

    async def continue_prompt(
        self,
        current_user_request: str,
        selected_task: types.SelectedTaskContext,
        retrieved_memories: RetrievedMemoryContext,
    ) -> types.VoicePromptContinuation:
        database = await self._get_database()
        conversation = await current_conversation_history(
            database,
            self.session_id,
            self.conversation_id,
        )
        session_memories = await session_memory_contexts(
            database,
            self.session_id,
        )
        retrieved_graph = retrieved_memory_graph(retrieved_memories)
        relevance_memories = await self._relevance_memories(database)
        task_prompt_memories = await self._task_prompt_memories(database)
        inputs = {
            "current_user_request": current_user_request,
            "current_conversation": conversation,
            "session_memories": session_memories,
            "selected_task": selected_task,
            "retrieved_memories": retrieved_graph,
            "current_session_id": self.session_id,
            "relevance_memories": relevance_memories,
            "task_prompt_memories": task_prompt_memories,
        }
        if self._prompt_debug is None:
            self._prompt_debug = PromptLayerDebugSession.begin(
                current_user_request=current_user_request,
            )
        kwargs = client_kwargs(self.client_name)
        started_at = time.perf_counter()
        try:
            result = await baml.ContinueVoicePrompt_async(
                **inputs,
                **kwargs,
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
        try:
            await self._dump_continuation_prompt_layers(inputs, result, kwargs)
        except Exception:
            pass
        return result

    async def _dump_understanding_prompt_layers(
        self,
        inputs: Mapping[str, Any],
        result: types.VoicePromptUnderstanding,
        kwargs: dict[str, Any],
    ) -> None:
        choose_task_inputs = {
            "current_user_request": inputs["current_user_request"],
            "current_conversation": inputs["current_conversation"],
            "session_memories": inputs["session_memories"],
            "available_tasks": inputs["available_tasks"],
            "task_choice_memories": inputs["task_choice_memories"],
        }
        await self._write_prompt_layer(
            1,
            "choose_task",
            inputs=choose_task_inputs,
            result=result.task_choice,
            elapsed_seconds=_seconds_from_ms(result.timings.task_choice_ms),
            build_request=lambda: baml.ChooseTask__build_request_async(
                **choose_task_inputs,
                **kwargs,
            ),
        )

        memory_search_inputs = {
            "current_user_request": inputs["current_user_request"],
            "current_conversation": inputs["current_conversation"],
            "session_memories": inputs["session_memories"],
            "selected_task": result.selected_task,
            "conversation_evaluation_memories": (
                inputs["conversation_evaluation_memories"]
            ),
        }
        await self._write_prompt_layer(
            2,
            "choose_memory_search",
            inputs=memory_search_inputs,
            result=result.memory_search_hints,
            elapsed_seconds=_seconds_from_ms(result.timings.memory_search_ms),
            build_request=lambda: baml.ChooseMemorySearch__build_request_async(
                **memory_search_inputs,
                **kwargs,
            ),
        )

        search_depth_inputs = {
            "current_timestamp": inputs["current_timestamp"],
            "current_user_request": inputs["current_user_request"],
            "current_conversation": inputs["current_conversation"],
            "session_memories": inputs["session_memories"],
            "selected_task": result.selected_task,
            "memory_search_hints": result.memory_search_hints,
            "search_domains": await baml.MemorySearchDomains_async(),
            "search_depth_memories": inputs["search_depth_memories"],
        }
        await self._write_prompt_layer(
            3,
            "choose_memory_search_depths",
            inputs=search_depth_inputs,
            result=result.search_depths,
            elapsed_seconds=_seconds_from_ms(result.timings.search_depth_ms),
            build_request=lambda: baml.ChooseMemorySearchDepths__build_request_async(
                **search_depth_inputs,
                **kwargs,
            ),
        )

    async def _dump_continuation_prompt_layers(
        self,
        inputs: Mapping[str, Any],
        result: types.VoicePromptContinuation,
        kwargs: dict[str, Any],
    ) -> None:
        candidate_memories = await baml.MemoryCandidates_async(
            inputs["retrieved_memories"],
            inputs["current_session_id"],
        )
        relevance_inputs = {
            "current_user_request": inputs["current_user_request"],
            "current_conversation": inputs["current_conversation"],
            "session_memories": inputs["session_memories"],
            "selected_task": inputs["selected_task"],
            "candidate_memories": candidate_memories,
            "relevance_memories": inputs["relevance_memories"],
        }
        await self._write_prompt_layer(
            5,
            "select_relevant_memories",
            inputs=relevance_inputs,
            result=result.relevance_decision,
            elapsed_seconds=_seconds_from_ms(result.timings.memory_relevance_ms),
            build_request=lambda: baml.SelectRelevantMemories__build_request_async(
                **relevance_inputs,
                **kwargs,
            ),
        )

        composition = _task_prompt_composition_from_decision(result.task_prompt)
        composition_inputs = {
            "current_user_request": inputs["current_user_request"],
            "current_conversation": inputs["current_conversation"],
            "session_memories": inputs["session_memories"],
            "selected_task": inputs["selected_task"],
            "selected_memories": result.selected_memory_contexts,
            "task_prompt_memories": inputs["task_prompt_memories"],
        }
        await self._write_prompt_layer(
            6,
            "compose_task_input",
            inputs=composition_inputs,
            result=composition,
            elapsed_seconds=_seconds_from_ms(result.timings.task_prompt_ms),
            build_request=lambda: baml.ComposeTaskInput__build_request_async(
                **composition_inputs,
                **kwargs,
            ),
        )

    async def _write_prompt_layer(
        self,
        order: int,
        name: str,
        *,
        inputs: Mapping[str, Any],
        result: Any,
        elapsed_seconds: float | None,
        build_request: Callable[[], Awaitable[Any]],
    ) -> None:
        if self._prompt_debug is None:
            return
        request = None
        debug_inputs: Mapping[str, Any] = inputs
        try:
            request = await build_request()
        except Exception as error:
            debug_inputs = {
                **inputs,
                "_debug_request_error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            }
        self._prompt_debug.write_layer(
            order=order,
            name=name,
            inputs=debug_inputs,
            result=result,
            request=request,
            elapsed_seconds=elapsed_seconds,
        )

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
        if self._prompt_debug is None:
            return
        self._prompt_debug.write_layer(
            order=order,
            name=name,
            inputs=inputs,
            result=result,
            elapsed_seconds=elapsed_seconds,
            error=error,
        )

    async def task_name(self, task_id: str) -> str | None:
        database = await self._get_database()
        task = await database.tasks.get(task_id)
        if task is None:
            return None
        return task.content.name

    async def close(self) -> None:
        if self.database is not None and self._owns_database:
            await self.database.close()
            self.database = None

    async def _get_database(self) -> MemoryDatabase:
        if self.database is None:
            self.database = await open_memory_database()
            await self.database.apply_schema()
            await self.database.ensure_roots()
        return self.database

    async def _available_tasks(
        self,
        database: MemoryDatabase,
    ) -> list[types.AvailableTask]:
        tasks = await database.tasks.search()
        return [
            types.AvailableTask(
                id=task.id,
                name=task.content.name,
                description=task.content.description,
                input=task.content.input,
                output=task.content.output,
                prompt=task.content.prompt,
                provider_id=task.content.provider_id,
                **timestamp_fields(task),
            )
            for task in tasks
        ]

    async def _task_choice_memories(
        self,
        database: MemoryDatabase,
    ) -> list[types.TaskChoiceMemoryContext]:
        memories = await database.task_choice_memories.search()
        return [
            types.TaskChoiceMemoryContext(
                title=memory.content.title,
                description=memory.content.description,
                tags=list(memory.tags),
                **timestamp_fields(memory),
            )
            for memory in memories
        ]

    async def _conversation_evaluation_memories(
        self,
        database: MemoryDatabase,
    ) -> list[types.ConversationEvaluationMemoryContext]:
        memories = await database.conversation_evaluation_memories.search()
        return [
            types.ConversationEvaluationMemoryContext(
                title=memory.content.title,
                description=memory.content.description,
                tags=list(memory.tags),
                **timestamp_fields(memory),
            )
            for memory in memories
        ]

    async def _search_depth_memories(
        self,
        database: MemoryDatabase,
    ) -> list[types.SearchDepthMemoryContext]:
        memories = await database.search_depth_memories.search()
        return [
            types.SearchDepthMemoryContext(
                title=memory.content.title,
                description=memory.content.description,
                tags=list(memory.tags),
                **timestamp_fields(memory),
            )
            for memory in memories
        ]

    async def _relevance_memories(
        self,
        database: MemoryDatabase,
    ) -> list[types.RelevanceMemoryContext]:
        memories = await database.relevance_memories.search()
        return [
            types.RelevanceMemoryContext(
                title=memory.content.title,
                description=memory.content.description,
                tags=list(memory.tags),
                **timestamp_fields(memory),
            )
            for memory in memories
        ]

    async def _task_prompt_memories(
        self,
        database: MemoryDatabase,
    ) -> list[types.TaskPromptMemoryContext]:
        memories = await database.task_prompt_memories.search()
        return [
            types.TaskPromptMemoryContext(
                title=memory.content.title,
                description=memory.content.description,
                tags=list(memory.tags),
                **timestamp_fields(memory),
            )
            for memory in memories
        ]


def _seconds_from_ms(milliseconds) -> float:
    return float(milliseconds) / 1000.0


def _task_prompt_composition_from_decision(
    decision: types.TaskPromptDecision,
) -> types.TaskPromptComposition:
    marker = "\n\nInput:\n"
    _task_prompt, separator, task_input = decision.full_task_prompt.partition(marker)
    return types.TaskPromptComposition(
        task_input=task_input if separator else decision.full_task_prompt,
        candidate_memory=decision.candidate_memory,
    )
