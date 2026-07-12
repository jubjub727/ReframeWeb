from __future__ import annotations

from dataclasses import dataclass, field

from baml_sdk import context as baml_context
from baml_sdk import task_routing as baml_task_routing
from reframe_agent_host.agent_flow.live_conversation import LiveConversationContext
from reframe_agent_host.agent_flow.memory_contexts import (
    available_tasks,
    conversation_evaluation_memories,
    relevance_memories,
    search_depth_memories,
    task_choice_memories,
    task_prompt_memories,
    user_preferences,
)
from reframe_agent_host.agent_flow.machine_state import (
    MachineStateProvider,
    local_machine_state_context,
)
from reframe_agent_host.agent_flow.retrieved_memory_graph import retrieved_memory_graph
from reframe_agent_host.agent_flow.session_context import (
    current_conversation_history,
    session_memory_contexts,
)
from reframe_agent_host.agent_flow.timestamps import current_timestamp
from reframe_memory import MemoryDatabase, open_memory_database
from reframe_memory.retrieved_context import RetrievedMemoryContext


@dataclass
class VoiceTurnContext:
    database: MemoryDatabase | None = None
    session_id: str | None = None
    conversation_id: str | None = None
    machine_state_provider: MachineStateProvider | None = None
    live_conversation: LiveConversationContext | None = None
    _owns_database: bool = field(init=False)

    def __post_init__(self) -> None:
        self._owns_database = self.database is None

    async def understanding_inputs(self, current_user_request: str) -> dict:
        database = await self._get_database()
        conversation = self._merge_live_conversation(
            await current_conversation_history(
                database,
                self.session_id,
                self.conversation_id,
            )
        )
        return {
            "current_timestamp": current_timestamp(),
            "current_user_request": current_user_request,
            "current_conversation": conversation,
            "session_memories": await session_memory_contexts(
                database, self.session_id
            ),
            "user_preferences": await user_preferences(database),
            "available_tasks": await available_tasks(database),
            "task_choice_memories": await task_choice_memories(database),
            "conversation_evaluation_memories": await conversation_evaluation_memories(
                database
            ),
            "search_depth_memories": await search_depth_memories(database),
            "machine_state": self._machine_state_context(),
        }

    async def continuation_inputs(
        self,
        current_user_request: str,
        selected_task: baml_task_routing.SelectedTaskContext,
        retrieved_memories: RetrievedMemoryContext,
    ) -> dict:
        database = await self._get_database()
        conversation = self._merge_live_conversation(
            await current_conversation_history(
                database,
                self.session_id,
                self.conversation_id,
            )
        )
        return {
            "current_user_request": current_user_request,
            "current_conversation": conversation,
            "session_memories": await session_memory_contexts(
                database, self.session_id
            ),
            "user_preferences": await user_preferences(database),
            "selected_task": selected_task,
            "retrieved_memories": retrieved_memory_graph(retrieved_memories),
            "current_session_id": self.session_id,
            "relevance_memories": await relevance_memories(database),
            "task_prompt_memories": await task_prompt_memories(database),
            "machine_state": self._machine_state_context(),
        }

    async def task_name(self, task_id: str) -> str | None:
        task = await (await self._get_database()).tasks.get(task_id)
        return None if task is None else task.content.name

    async def close(self) -> None:
        if self.database is not None and self._owns_database:
            await self.database.close()
            self.database = None

    async def _get_database(self) -> MemoryDatabase:
        if self.database is None:
            self.database = await open_memory_database()
        return self.database

    def _machine_state_context(self) -> baml_context.MachineStateContext:
        if self.machine_state_provider is None:
            return local_machine_state_context("No voice startup machine state provider")
        return self.machine_state_provider.context()

    def _merge_live_conversation(
        self,
        conversation: baml_context.ConversationHistory | None,
    ) -> baml_context.ConversationHistory | None:
        if self.live_conversation is None:
            return conversation
        return self.live_conversation.merge(conversation, self.conversation_id)
