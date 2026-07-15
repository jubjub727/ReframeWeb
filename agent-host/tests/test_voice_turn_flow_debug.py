from __future__ import annotations

from datetime import datetime, timezone
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from baml_sdk import memory as baml_memory
from baml_sdk import task_catalog as baml_task_catalog
from baml_sdk import task as baml_task
from baml_sdk import voice_turn as baml_voice_turn
from reframe_agent_host.agent_flow.voice_turn_flow import BamlVoiceTurnFlow
from reframe_memory import MemoryNode, MemoryTimestamps, Provider, RetrievedMemoryContext, Task


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

    async def test_top_level_flow_records_inlined_layers_and_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            flow = BamlVoiceTurnFlow(database=_FakeDatabase())
            with mock.patch(
                "reframe_agent_host.agent_flow.prompt_layer_debug._dump_dir",
                return_value=Path(temp_dir),
            ):
                with _mock_baml_calls():
                    inputs = {
                        "current_user_request": "Tell me a joke.",
                        **await flow.voice_turn_inputs("Tell me a joke."),
                    }
                    understanding = await _understand()
                    await flow.record_understanding(inputs, understanding)
                    retrieved = baml_memory.RetrievedMemoryGraph(
                        task_catalog=[],
                        past_sessions=[],
                        current_session_memories=[],
                    )
                    continuation = await _continue()
                    await flow.record_continuation(
                        inputs,
                        understanding.selected_task,
                        retrieved,
                        continuation,
                    )
                    result = _voice_task_result(
                        understanding,
                        continuation,
                        retrieved,
                    )
                    with mock.patch(
                        "reframe_agent_host.agent_flow.voice_turn_flow."
                        "baml_voice_turn.RunVoiceTurn_async",
                        return_value=result,
                    ):
                        with mock.patch(
                            "reframe_agent_host.agent_flow.task_review_debug."
                            "baml_task.CheckTaskCompletion__build_request_async",
                            return_value=_Request("CheckTaskCompletion"),
                        ):
                            await flow.run_voice_turn("Tell me a joke.", _Host())

            latest = Path(temp_dir) / "latest"
            layer_names = sorted(path.name for path in latest.glob("*.json"))

        self.assertEqual(
            layer_names,
            [
                "00-understand_voice_prompt.json",
                "01-choose_task.json",
                "02-choose_memory_search.json",
                "03-choose_memory_search_depths.json",
                "04-continue_voice_prompt.json",
                "05-select_relevant_memories.json",
                "06-compose_task_input.json",
                "09-check_task_completion.json",
                "index.json",
            ],
        )


class _FakeDatabase:
    def __init__(self) -> None:
        self.tasks = _SearchStore([_task_node()])
        self.providers = _SearchStore([_provider_node()])
        self.user_preferences = _SearchStore([])
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


class _Host:
    callbacks = {}


def _mock_baml_calls():
    patches = [
        mock.patch(
            "reframe_agent_host.agent_flow.voice_turn_flow.baml_voice_turn.UnderstandVoicePrompt_async",
            side_effect=_understand,
        ),
        mock.patch(
            "reframe_agent_host.agent_flow.voice_turn_flow.baml_voice_turn.ContinueVoicePrompt_async",
            side_effect=_continue,
        ),
    ]
    build_requests = {
        "ChooseTask": "baml_task",
        "ChooseMemorySearch": "baml_memory",
        "ChooseMemorySearchDepths": "baml_memory",
        "SelectRelevantMemories": "baml_memory",
        "ComposeTaskInput": "baml_task",
    }
    for name, module in build_requests.items():
        patches.append(
            mock.patch(
                "reframe_agent_host.agent_flow.voice_prompt_debug."
                f"{module}.{name}__build_request_async",
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
    return baml_voice_turn.VoicePromptUnderstanding(
        task_choice=baml_task.TaskChoiceDecision(
            selected_task_id="memory_node:reply",
            confidence=1.0,
            candidate_memory=None,
        ),
        selected_task=_selected_task(),
        memory_search_hints=baml_memory.ConversationMemorySearchHints(
            tags=baml_memory.MemoryTagSearch(any_of=[], all_of=[], none_of=[]),
            strings=baml_memory.MemoryStringSearch(contains=[], equals=[]),
            candidate_memory=None,
        ),
        search_depths=baml_memory.SearchDepthDecision(
            depths={
                "task_catalog": baml_memory.SearchDepthTimestamps(
                    created_after="2026-01-01T00:00:00Z",
                    read_after="2026-01-01T00:00:00Z",
                    updated_after="2026-01-01T00:00:00Z",
                ),
            },
            candidate_memory=None,
        ),
        timings=baml_voice_turn.VoicePromptUnderstandingTimings(
            task_choice_ms=10,
            memory_search_ms=20,
            search_depth_ms=30,
        ),
    )


async def _continue(**_kwargs):
    return baml_voice_turn.VoicePromptContinuation(
        relevance_decision=baml_memory.RelevantMemoryDecision(
            kept_memory_ids=[],
            candidate_memory=None,
        ),
        selected_memories=baml_memory.RetrievedMemoryGraph(
            task_catalog=[],
            past_sessions=[],
            current_session_memories=[],
        ),
        selected_memory_contexts=[],
        task_prompt=baml_task.TaskPromptDecision(
            full_task_prompt="Task:\nReply.\n\nInput:\nTell me a joke.",
            candidate_memory=None,
        ),
        timings=baml_voice_turn.VoicePromptContinuationTimings(
            memory_relevance_ms=40,
            task_prompt_ms=50,
        ),
    )


def _selected_task() -> baml_task_catalog.SelectedTaskContext:
    return baml_task_catalog.SelectedTaskContext(
        id="memory_node:reply",
        name="Reply to user",
        description="Reply directly.",
        input="The user's message.",
        output="agent_reply",
        prompt="Reply.",
        provider_id="memory_node:provider",
        model_id="glm-5.1",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        read_at="NONE",
    )


def _voice_task_result(understanding, continuation, retrieved):
    completion = baml_voice_turn.VoiceTaskCompletionReview(
        attempt_id="attempt-1",
        completion_string="agent_reply",
        output_summary="The user received a useful reply.",
        completion=baml_task.CompletionResult.PASS,
        elapsed_ms=75,
    )
    return baml_voice_turn.VoiceTaskFlowResult(
        cycle_id="cycle-1",
        understanding=understanding,
        retrieved_memories=retrieved,
        continuation=continuation,
        attempt_id="attempt-1",
        task_completion=baml_task.CompletionResult.PASS,
        task_completion_ms=75,
        completion_reviews=[completion],
        failure_reviews=[],
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


def _provider_node() -> MemoryNode[Provider]:
    return MemoryNode(
        id="memory_node:provider",
        tags=("provider",),
        timestamps=_timestamps(),
        content=Provider(
            name="Test provider",
            description="Test provider.",
            baml_surface="TaskPromptModel",
            model_id="glm-5.1",
        ),
    )


def _timestamps() -> MemoryTimestamps:
    now = datetime.now(timezone.utc)
    return MemoryTimestamps(created_at=now, updated_at=now, read_at=None)


if __name__ == "__main__":
    unittest.main()
