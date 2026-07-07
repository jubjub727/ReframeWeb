from __future__ import annotations

from datetime import datetime, timezone
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import baml_sdk as types
from reframe_agent_host.agent_flow.voice_turn_flow import BamlVoiceTurnFlow
from reframe_memory import MemoryNode, MemoryTimestamps, RetrievedMemoryContext, Task


class VoiceTurnFlowDebugTests(unittest.IsolatedAsyncioTestCase):
    async def test_flow_writes_prompt_layer_dumps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            flow = BamlVoiceTurnFlow(database=_FakeDatabase())
            with mock.patch(
                "reframe_agent_host.agent_flow.prompt_layer_debug._dump_dir",
                return_value=Path(temp_dir),
            ):
                with _mock_baml_calls():
                    understanding = await flow.understand_prompt("Tell me a joke.")
                    await flow.continue_prompt(
                        "Tell me a joke.",
                        understanding.selected_task,
                        RetrievedMemoryContext(),
                    )

            latest_dir = Path(temp_dir) / "latest"
            layer_names = sorted(path.name for path in latest_dir.glob("*.json"))
            compose = json.loads(
                (latest_dir / "06-compose_task_input.json").read_text(
                    encoding="utf-8",
                ),
            )

        self.assertIn("00-understand_voice_prompt.json", layer_names)
        self.assertIn("01-choose_task.json", layer_names)
        self.assertIn("02-choose_memory_search.json", layer_names)
        self.assertIn("03-choose_memory_search_depths.json", layer_names)
        self.assertIn("04-continue_voice_prompt.json", layer_names)
        self.assertIn("05-select_relevant_memories.json", layer_names)
        self.assertIn("06-compose_task_input.json", layer_names)
        self.assertEqual(compose["result"]["task_input"], "Tell me a joke.")


class _FakeDatabase:
    def __init__(self) -> None:
        self.tasks = _SearchStore([_task_node()])
        self.task_choice_memories = _SearchStore([])
        self.conversation_evaluation_memories = _SearchStore([])
        self.search_depth_memories = _SearchStore([])
        self.relevance_memories = _SearchStore([])
        self.task_prompt_memories = _SearchStore([])


class _SearchStore:
    def __init__(self, items) -> None:
        self._items = items

    async def search(self):
        return self._items


class _Request:
    def __init__(self, label: str) -> None:
        self.body = json.dumps(
            {
                "model": "debug-model",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": label,
                            },
                        ],
                    },
                ],
            },
        )


def _mock_baml_calls():
    patches = [
        mock.patch(
            "reframe_agent_host.agent_flow.voice_turn_flow.baml.UnderstandVoicePrompt_async",
            side_effect=_understand,
        ),
        mock.patch(
            "reframe_agent_host.agent_flow.voice_turn_flow.baml.ContinueVoicePrompt_async",
            side_effect=_continue,
        ),
    ]
    for name in (
        "ChooseTask",
        "ChooseMemorySearch",
        "ChooseMemorySearchDepths",
        "SelectRelevantMemories",
        "ComposeTaskInput",
    ):
        patches.append(
            mock.patch(
                "reframe_agent_host.agent_flow.voice_turn_flow.baml."
                f"{name}__build_request_async",
                side_effect=lambda *args, _name=name, **kwargs: _Request(_name),
            ),
        )
    return _PatchStack(patches)


class _PatchStack:
    def __init__(self, patches) -> None:
        self._patches = patches

    def __enter__(self):
        for patch in self._patches:
            patch.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        for patch in reversed(self._patches):
            patch.__exit__(exc_type, exc, traceback)


async def _understand(**_kwargs):
    return types.VoicePromptUnderstanding(
        task_choice=types.TaskChoiceDecision(
            selected_task_id="memory_node:reply",
            confidence=1.0,
            agent_thought=None,
            candidate_memory=None,
        ),
        selected_task=_selected_task(),
        memory_search_hints=types.ConversationMemorySearchHints(
            tags=types.MemoryTagSearch(any_of=[], all_of=[], none_of=[]),
            strings=types.MemoryStringSearch(contains=[], equals=[]),
            candidate_memory=None,
        ),
        search_depths=types.SearchDepthDecision(
            depths={
                "task_catalog": types.SearchDepthTimestamps(
                    created_after="2026-01-01T00:00:00Z",
                    read_after="2026-01-01T00:00:00Z",
                    updated_after="2026-01-01T00:00:00Z",
                ),
            },
            candidate_memory=None,
        ),
        timings=types.VoicePromptUnderstandingTimings(
            task_choice_ms=10,
            memory_search_ms=20,
            search_depth_ms=30,
        ),
    )


async def _continue(**_kwargs):
    return types.VoicePromptContinuation(
        relevance_decision=types.RelevantMemoryDecision(
            kept_memory_ids=[],
            candidate_memory=None,
        ),
        selected_memories=types.RetrievedMemoryGraph(
            task_catalog=[],
            past_sessions=[],
            current_session_memories=[],
        ),
        selected_memory_contexts=[],
        task_prompt=types.TaskPromptDecision(
            full_task_prompt="Task:\nReply.\n\nInput:\nTell me a joke.",
            candidate_memory=None,
        ),
        timings=types.VoicePromptContinuationTimings(
            memory_relevance_ms=40,
            task_prompt_ms=50,
        ),
    )


def _selected_task() -> types.SelectedTaskContext:
    return types.SelectedTaskContext(
        id="memory_node:reply",
        name="Reply to user",
        description="Reply directly.",
        input="The user's message.",
        output="agent_reply",
        prompt="Reply.",
        provider_id="memory_node:provider",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        read_at="NONE",
    )


def _task_node() -> MemoryNode[Task]:
    return MemoryNode(
        id="memory_node:reply",
        tags=("reply",),
        timestamps=_timestamps(),
        content=Task(
            name="Reply to user",
            description="Reply directly.",
            input="The user's message.",
            output="agent_reply",
            prompt="Reply.",
            provider_id="memory_node:provider",
        ),
    )


def _timestamps() -> MemoryTimestamps:
    now = datetime.now(timezone.utc)
    return MemoryTimestamps(created_at=now, updated_at=now, read_at=None)


if __name__ == "__main__":
    unittest.main()
