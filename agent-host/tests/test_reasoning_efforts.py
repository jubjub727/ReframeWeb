import json
import unittest
from datetime import datetime, timezone

import baml_sdk as baml
import baml_sdk as types
from reframe_agent_host.agent_flow.baml_clients import client_kwargs
from reframe_agent_host.benchmarks.reasoning_efforts import (
    opencode_reasoning_effort_candidates,
    opencode_reasoning_effort_client,
    unsupported_reasoning_effort_error,
)
from reframe_agent_host.commands.parser import build_parser
from reframe_memory import MemoryNode, MemoryTimestamps, Provider


class ReasoningEffortBenchmarkTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_task_choice_client_uses_kimi_k25_high(self):
        request = await baml.ChooseTask__build_request_async(
            current_user_request="Install the missing GPU driver for me.",
            current_conversation=None,
            session_memories=[],
            available_tasks=[
                types.AvailableTask(
                    id="task:cannot_handle",
                    name="Explain request cannot be handled",
                    description="Use when the request is unsupported.",
                    input="The user's request.",
                    output="A task choice.",
                    prompt="Explain the limitation.",
                    provider_id="provider:test",
                    created_at="2026-07-03T00:00:00Z",
                    updated_at="2026-07-03T00:00:00Z",
                    read_at="NONE",
                )
            ],
            task_choice_memories=[],
        )
        body = json.loads(request.body)

        self.assertEqual(body["model"], "kimi-k2.5")
        self.assertEqual(body["reasoning_effort"], "high")

    async def test_compiled_client_adds_reasoning_effort_to_request(self):
        client, client_name = opencode_reasoning_effort_client(
            _provider("OpenCodeGoModelDeepseekV4Pro"),
            "low",
        )

        request = await baml.ChooseTask__build_request_async(
            current_user_request="Test routing.",
            current_conversation=None,
            session_memories=[],
            available_tasks=[
                types.AvailableTask(
                    id="task:test",
                    name="Test task",
                    description="Used by the benchmark request test.",
                    input="A transcript.",
                    output="A task choice.",
                    prompt="Choose the task.",
                    provider_id="provider:test",
                    created_at="2026-07-03T00:00:00Z",
                    updated_at="2026-07-03T00:00:00Z",
                    read_at="NONE",
                )
            ],
            task_choice_memories=[],
            **client_kwargs(client),
        )
        body = json.loads(request.body)

        self.assertEqual(client_name, "OpenCodeGoModelDeepseekV4ProReasoningLow")
        self.assertEqual(body["model"], "deepseek-v4-pro")
        self.assertEqual(body["reasoning_effort"], "low")

    def test_reasoning_effort_candidates_are_model_specific(self):
        candidates = ("high", "xhigh", "max")

        self.assertEqual(
            opencode_reasoning_effort_candidates(
                _provider("OpenCodeGoModelKimiK26"),
                candidates,
            ),
            ("high", "xhigh"),
        )
        self.assertEqual(
            opencode_reasoning_effort_candidates(
                _provider("OpenCodeGoModelDeepseekV4Flash"),
                candidates,
            ),
            ("high", "max"),
        )

    async def test_compiled_client_adds_reasoning_effort_to_search_depth_request(self):
        client, client_name = opencode_reasoning_effort_client(
            _provider("OpenCodeGoModelGlm51"),
            "high",
        )

        request = await baml.ChooseMemorySearchDepths__build_request_async(
            current_timestamp="2026-07-03T15:00:00Z",
            current_user_request="Open Hacker News compactly.",
            current_conversation=None,
            session_memories=[],
            selected_task=types.SelectedTaskContext(
                id="task:visual_panel",
                name="Visual panel",
                description="Open a visual panel.",
                input="A request.",
                output="A rendered panel.",
                prompt="Use the store and panel.",
                provider_id="provider:test",
                created_at="2026-07-03T00:00:00Z",
                updated_at="2026-07-03T00:00:00Z",
                read_at="NONE",
            ),
            memory_search_hints=types.ConversationMemorySearchHints(
                tags=types.MemoryTagSearch(any_of=[], all_of=[], none_of=[]),
                strings=types.MemoryStringSearch(contains=[], equals=[]),
                candidate_memory=None,
            ),
            search_domains=[
                types.SearchDepthDomain(
                    id="task_catalog",
                    description="Task records.",
                    searches="Task nodes.",
                    hydrates="Task nodes.",
                )
            ],
            search_depth_memories=[],
            **client_kwargs(client),
        )
        body = json.loads(request.body)

        self.assertEqual(client_name, "OpenCodeGoModelGlm51ReasoningHigh")
        self.assertEqual(body["model"], "glm-5.1")
        self.assertEqual(body["reasoning_effort"], "high")

    async def test_default_relevance_client_uses_glm51_none(self):
        request = await baml.SelectRelevantMemories__build_request_async(
            current_user_request="Open Hacker News compactly.",
            current_conversation=None,
            session_memories=[],
            selected_task=types.SelectedTaskContext(
                id="task:visual_panel",
                name="Visual panel",
                description="Open a visual panel.",
                input="A request.",
                output="A rendered panel.",
                prompt="Use the store and panel.",
                provider_id="provider:test",
                created_at="2026-07-03T00:00:00Z",
                updated_at="2026-07-03T00:00:00Z",
                read_at="NONE",
            ),
            candidate_memories=[
                types.RetrievedMemoryCandidate(
                    id="memory_node:message1",
                    kind="past_conversation_message",
                    title="human message",
                    description="Use compact rows for Hacker News.",
                    tags=[],
                    created_at="2026-07-03T00:00:00Z",
                    updated_at="2026-07-03T00:00:00Z",
                    read_at="NONE",
                    retrieval_matched=True,
                    parent_session_id="memory_node:session1",
                    parent_conversation_id="memory_node:conversation1",
                )
            ],
            relevance_memories=[],
        )
        body = json.loads(request.body)

        self.assertEqual(body["model"], "glm-5.1")
        self.assertEqual(body["reasoning_effort"], "none")

    def test_unsupported_reasoning_effort_detection_is_narrow(self):
        self.assertTrue(
            unsupported_reasoning_effort_error(
                Exception("400 Bad Request invalid_request_error")
            )
        )
        self.assertFalse(unsupported_reasoning_effort_error(Exception("503 busy")))

    def test_task_choice_parser_accepts_reasoning_effort_flags(self):
        args = build_parser().parse_args(
            [
                "benchmark-task-choice",
                "--reasoning-effort",
                "low",
                "--reasoning-effort",
                "medium",
                "--reasoning-effort-candidate",
                "high",
            ]
        )

        self.assertEqual(args.reasoning_efforts, ["low", "medium"])
        self.assertEqual(args.reasoning_effort_candidates, ["high"])

    def test_conversation_parser_accepts_reasoning_effort_flags(self):
        args = build_parser().parse_args(
            [
                "benchmark-conversation-evaluation",
                "--reasoning-effort",
                "low",
                "--reasoning-effort-candidate",
                "minimal",
            ]
        )

        self.assertEqual(args.reasoning_efforts, ["low"])
        self.assertEqual(args.reasoning_effort_candidates, ["minimal"])

    def test_control_flow_parser_accepts_reasoning_effort_flags(self):
        args = build_parser().parse_args(
            [
                "benchmark-control-flow",
                "--reasoning-effort",
                "low",
                "--reasoning-effort-candidate",
                "high",
            ]
        )

        self.assertEqual(args.reasoning_efforts, ["low"])
        self.assertEqual(args.reasoning_effort_candidates, ["high"])


def _provider(surface: str):
    now = datetime.now(timezone.utc)
    return MemoryNode(
        id="provider:test",
        tags=(),
        timestamps=MemoryTimestamps(
            created_at=now,
            updated_at=now,
            read_at=None,
        ),
        content=Provider(
            name="Test provider",
            description="Used by reasoning effort tests.",
            baml_surface=surface,
        ),
    )


if __name__ == "__main__":
    unittest.main()
