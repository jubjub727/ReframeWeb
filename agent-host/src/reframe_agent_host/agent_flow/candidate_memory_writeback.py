from __future__ import annotations

from reframe_memory.models import ContextMemory


async def write_candidate_memories(database, batch) -> None:
    destinations = (
        (database.task_choice_memories, batch.task_choice),
        (
            database.conversation_evaluation_memories,
            batch.conversation_evaluation,
        ),
        (database.search_depth_memories, batch.search_depth),
        (database.relevance_memories, batch.relevance),
        (database.task_prompt_memories, batch.task_prompt),
    )
    for store, candidates in destinations:
        for candidate in candidates:
            await store.create(
                ContextMemory(
                    title=candidate.title,
                    description=candidate.description,
                )
            )
