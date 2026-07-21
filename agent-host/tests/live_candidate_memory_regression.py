from __future__ import annotations

import asyncio

from baml_sdk import memory as baml_memory
from baml_sdk import task as baml_task
from baml_sdk import task_catalog as baml_task_catalog
from baml_sdk import turn_context as baml_turn_context

from reframe_agent_host.agent_flow.machine_state import local_machine_state_context


REQUEST = "when you reply with numbers, can you include the commas"
CREATED_AT = "2026-07-21T00:00:00Z"


def _available_task():
    return baml_task_catalog.AvailableTask(
        id="reply",
        name="Reply to user",
        description="Reply usefully to the active request.",
        input="The active user request.",
        output="The user received a useful spoken reply.",
        prompt="Reply to the user.",
        provider_id="test",
        model_id="test",
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
        read_at=CREATED_AT,
    )


def _selected_task():
    task = _available_task()
    return baml_task_catalog.SelectedTaskContext(**task.model_dump())


def _session_memory():
    return baml_turn_context.SessionMemoryContext(
        title="Use comma separators in large numbers",
        description="Format large numeric answers with comma thousands separators.",
        tags=["formatting", "numbers"],
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
        read_at=CREATED_AT,
    )


async def _run() -> dict[str, object | None]:
    machine_state = local_machine_state_context("candidate-memory-regression")
    selected_task = _selected_task()
    session_memory = _session_memory()
    task_choice = await baml_task.ChooseTask_async(
        current_user_request=REQUEST,
        current_conversation=None,
        session_memories=[],
        user_preferences=[
            baml_turn_context.UserPreferenceMemoryContext(
                id="formatting-preference",
                title=session_memory.title,
                description=session_memory.description,
                tags=session_memory.tags,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
                read_at=CREATED_AT,
            )
        ],
        available_tasks=[_available_task()],
        task_choice_memories=[],
        machine_state=machine_state,
    )
    search_hints = await baml_memory.ChooseMemorySearch_async(
        current_user_request=REQUEST,
        current_conversation=None,
        session_memories=[session_memory],
        selected_task=selected_task,
        conversation_evaluation_memories=[],
        machine_state=machine_state,
    )
    search_depth = await baml_memory.ChooseMemorySearchDepths_async(
        current_timestamp=CREATED_AT,
        current_user_request=REQUEST,
        current_conversation=None,
        session_memories=[session_memory],
        selected_task=selected_task,
        memory_search_hints=search_hints,
        search_domains=[
            baml_memory.SearchDepthDomain(
                id="user_preferences",
                description="Durable user preference memories.",
                searches="User preference nodes.",
                hydrates="Matching user preference nodes.",
            )
        ],
        search_depth_memories=[],
        machine_state=machine_state,
    )
    relevance = await baml_memory.SelectRelevantMemories_async(
        current_user_request=REQUEST,
        current_conversation=None,
        session_memories=[session_memory],
        selected_task=selected_task,
        candidate_memories=[
            baml_memory.RetrievedMemoryCandidate(
                id="formatting-preference",
                kind="user_preference",
                title=session_memory.title,
                description=session_memory.description,
                tags=session_memory.tags,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
                read_at=CREATED_AT,
                retrieval_matched=True,
                parent_session_id=None,
                parent_conversation_id=None,
            )
        ],
        relevance_memories=[],
        machine_state=machine_state,
    )
    composition = await baml_task.ComposeTaskInput_async(
        current_user_request=REQUEST,
        current_conversation=None,
        session_memories=[session_memory],
        selected_task=selected_task,
        selected_memories=[],
        task_prompt_memories=[],
        machine_state=machine_state,
    )
    return {
        "task_choice": task_choice.candidate_memory,
        "memory_search": search_hints.candidate_memory,
        "search_depth": search_depth.candidate_memory,
        "memory_relevance": relevance.candidate_memory,
        "task_prompt": composition.candidate_memory,
    }


def main() -> int:
    candidates = asyncio.run(_run())
    unexpected = {layer: value for layer, value in candidates.items() if value is not None}
    if unexpected:
        for layer, value in unexpected.items():
            print(f"{layer}: {value}")
        return 1
    print("passed 5/5 candidate-memory layer decisions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
