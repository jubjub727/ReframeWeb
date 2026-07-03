import unittest
from datetime import datetime, timezone

from reframe_agent_host.baml_client import b, types
from reframe_agent_host.benchmarks.reasoning_efforts import (
    opencode_reasoning_effort_client,
    unsupported_reasoning_effort_error,
)
from reframe_agent_host.commands.parser import build_parser
from reframe_memory import MemoryNode, MemoryTimestamps, Provider


class ReasoningEffortBenchmarkTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_task_choice_client_uses_kimi_k25_high(self):
        request = await b.request.ChooseInitialTask(
            current_user_request="Install the missing GPU driver for me.",
            session_conversations=[],
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
        body = request.body.json()

        self.assertEqual(body["model"], "kimi-k2.5")
        self.assertEqual(body["reasoning_effort"], "high")

    async def test_dynamic_client_adds_reasoning_effort_to_request(self):
        client, client_name = opencode_reasoning_effort_client(
            _provider("OpenCodeGoModelDeepseekV4Pro"),
            "low",
        )

        request = await client.request.ChooseInitialTask(
            current_user_request="Test routing.",
            session_conversations=[],
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
        )
        body = request.body.json()

        self.assertEqual(client_name, "OpenCodeGoModelDeepseekV4ProReasoningLow")
        self.assertEqual(body["model"], "deepseek-v4-pro")
        self.assertEqual(body["reasoning_effort"], "low")

    async def test_dynamic_client_adds_reasoning_effort_to_search_depth_request(self):
        client, client_name = opencode_reasoning_effort_client(
            _provider("OpenCodeGoModelGlm51"),
            "high",
        )

        request = await client.request.EvaluateSearchDepths(
            current_timestamp="2026-07-03T15:00:00Z",
            current_user_request="Open Hacker News compactly.",
            session_conversations=[],
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
        )
        body = request.body.json()

        self.assertEqual(client_name, "OpenCodeGoModelGlm51ReasoningHigh")
        self.assertEqual(body["model"], "glm-5.1")
        self.assertEqual(body["reasoning_effort"], "high")

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
