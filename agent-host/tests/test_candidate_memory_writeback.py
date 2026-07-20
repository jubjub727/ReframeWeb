from __future__ import annotations

import unittest

from baml_sdk import memory as baml_memory
from reframe_agent_host.agent_flow.candidate_memory_writeback import (
    write_candidate_memories,
)


class CandidateMemoryWritebackTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_groups_append_to_their_matching_roots(self) -> None:
        database = _Database()
        await write_candidate_memories(
            database,
            baml_memory.CandidateMemoryWriteBatch(
                task_choice=[_candidate("task-choice-1", "Route")],
                conversation_evaluation=[],
                search_depth=[_candidate("search-depth-1", "Depth")],
                relevance=[],
                task_prompt=[_candidate("task-prompt-1", "Prompt")],
            ),
        )

        self.assertEqual(_titles(database.task_choice_memories), ["Route"])
        self.assertEqual(_titles(database.search_depth_memories), ["Depth"])
        self.assertEqual(_titles(database.task_prompt_memories), ["Prompt"])
        self.assertEqual(database.conversation_evaluation_memories.created, [])
        self.assertEqual(database.relevance_memories.created, [])


class _Store:
    def __init__(self) -> None:
        self.created = []

    async def create(self, memory) -> None:
        self.created.append(memory)


class _Database:
    def __init__(self) -> None:
        self.task_choice_memories = _Store()
        self.conversation_evaluation_memories = _Store()
        self.search_depth_memories = _Store()
        self.relevance_memories = _Store()
        self.task_prompt_memories = _Store()


def _candidate(candidate_id: str, title: str):
    return baml_memory.CandidateMemoryEntry(
        id=candidate_id,
        title=title,
        description=f"{title} guidance",
    )


def _titles(store: _Store) -> list[str]:
    return [memory.title for memory in store.created]


if __name__ == "__main__":
    unittest.main()
