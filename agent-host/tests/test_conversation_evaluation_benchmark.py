import unittest
import json
from datetime import datetime, timezone
from tempfile import TemporaryDirectory

from baml_sdk import memory_search as baml_memory_search
from reframe_agent_host.agent_flow.machine_state import local_machine_state_context
from reframe_agent_host.benchmarks.conversation_evaluation_config import (
    CONVERSATION_EVALUATION_DEFAULT_MODEL_ID,
    CONVERSATION_EVALUATION_DEFAULT_REASONING_EFFORT,
    ConversationEvaluationBenchmarkConfig,
)
from reframe_agent_host.benchmarks.conversation_evaluation_result_analysis import (
    conversation_evaluation_case_analyses,
)
from reframe_agent_host.benchmarks.conversation_evaluation_cases import (
    conversation_evaluation_cases,
)
from reframe_agent_host.benchmarks.conversation_evaluation_context import (
    conversation_context,
    conversation_evaluation_memory_context,
    memory_context,
    selected_task_context,
)
from reframe_agent_host.benchmarks.conversation_evaluation_runner import (
    _conversation_evaluation_providers,
)
from reframe_agent_host.commands.parser import build_parser
from reframe_memory import MemoryNode, MemoryTimestamps, Provider


class ConversationEvaluationBenchmarkTests(unittest.TestCase):
    def test_cases_convert_to_baml_context_types(self):
        cases = conversation_evaluation_cases()

        self.assertGreaterEqual(len(cases), 3)
        for case in cases:
            self.assertTrue(case.id)
            self.assertTrue(case.current_user_request)
            selected_task = selected_task_context(case.selected_task)
            self.assertTrue(selected_task.name)
            self.assertTrue(selected_task.created_at)
            self.assertTrue(selected_task.updated_at)
            self.assertTrue(selected_task.read_at)
            for conversation in case.session_conversations:
                self.assertTrue(conversation.created_at)
                self.assertTrue(conversation.updated_at)
                self.assertTrue(conversation.read_at)
                self.assertNotEqual(conversation.messages[-1].role, "human")
                self.assertEqual(
                    conversation.messages[-2].content,
                    case.current_user_request,
                )
                for index, message in enumerate(conversation.messages):
                    self.assertTrue(message.created_at)
                    self.assertTrue(message.updated_at)
                    self.assertTrue(message.read_at)
                    if message.role == "human" and index > 0:
                        self.assertEqual(conversation.messages[index - 1].role, "agent")
            conversations = conversation_context(case.session_conversations)
            session_memories = memory_context(case.session_memories)
            evaluation_memories = conversation_evaluation_memory_context(
                case.conversation_evaluation_memories
            )
            self.assertTrue(conversations[0].created_at)
            for memory in session_memories + evaluation_memories:
                self.assertTrue(memory.created_at)
                self.assertTrue(memory.updated_at)
                self.assertTrue(memory.read_at)

    def test_parser_accepts_conversation_evaluation_benchmark(self):
        parser = build_parser()

        args = parser.parse_args(
            [
                "benchmark-conversation-evaluation",
                "--case-id",
                "remembered_view_preference",
                "--runs",
                "2",
            ]
        )

        self.assertEqual(args.command, "benchmark-conversation-evaluation")
        self.assertEqual(args.case_ids, ["remembered_view_preference"])
        self.assertEqual(args.runs, 2)

    def test_conversation_evaluation_defaults_to_glm51_none(self):
        config = ConversationEvaluationBenchmarkConfig(
            runs=1,
            warmup_runs=0,
            delay_seconds=0,
            provider_cooldown_seconds=0,
        )

        self.assertEqual(CONVERSATION_EVALUATION_DEFAULT_MODEL_ID, "glm-5.1")
        self.assertEqual(CONVERSATION_EVALUATION_DEFAULT_REASONING_EFFORT, "none")
        self.assertEqual(config.conversation_evaluation_model_id, "glm-5.1")
        self.assertEqual(config.reasoning_efforts, ("none",))

    def test_conversation_evaluation_default_provider_filter(self):
        providers = (
            _provider("provider:deepseek", "opencode_go.OpenCodeGoModelDeepseekV4Flash"),
            _provider("provider:glm51", "opencode_go.OpenCodeGoModelGlm51"),
        )
        config = ConversationEvaluationBenchmarkConfig(
            runs=1,
            warmup_runs=0,
            delay_seconds=0,
            provider_cooldown_seconds=0,
        )

        selected = _conversation_evaluation_providers(providers, config)

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].content.baml_surface, "opencode_go.OpenCodeGoModelGlm51")

    def test_parser_accepts_conversation_evaluation_analysis(self):
        parser = build_parser()

        args = parser.parse_args(
            [
                "analyze-conversation-evaluation-benchmark",
                "benchmark-results/conversation-evaluation-local.json",
            ]
        )

        self.assertEqual(args.command, "analyze-conversation-evaluation-benchmark")
        self.assertEqual(
            args.path,
            "benchmark-results/conversation-evaluation-local.json",
        )

    def test_analysis_orders_replies_by_latency(self):
        with TemporaryDirectory() as directory:
            path = f"{directory}/result.json"
            with open(path, "w", encoding="utf-8") as file:
                json.dump(
                    {
                        "cases": [
                            {
                                "id": "example",
                                "current_user_request": "Open Hacker News.",
                                "selected_task_name": "Prepare visual panel",
                                "review_focus": "Review hints.",
                            }
                        ],
                        "providers": [
                            {
                                "provider_id": "provider:slow",
                                "provider_name": "Slow",
                                "baml_surface": "SlowSurface",
                                "model_id": "slow-model",
                                "case_results": [
                                    {
                                        "case_id": "example",
                                        "run_index": 0,
                                        "latency_seconds": 2.0,
                                        "hints": {"tags": {}, "strings": {}},
                                    }
                                ],
                            },
                            {
                                "provider_id": "provider:fast",
                                "provider_name": "Fast",
                                "baml_surface": "FastSurface",
                                "model_id": "fast-model",
                                "case_results": [
                                    {
                                        "case_id": "example",
                                        "run_index": 0,
                                        "latency_seconds": 1.0,
                                        "hints": {
                                            "tags": {"any_of": ["hacker-news"]},
                                            "strings": {
                                                "contains": ["compact"],
                                                "equals": [],
                                            },
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    file,
                )

            analyses = conversation_evaluation_case_analyses(path)

        self.assertEqual(analyses[0].case_id, "example")
        self.assertEqual(analyses[0].replies[0].model_id, "fast-model")
        self.assertEqual(analyses[0].replies[1].model_id, "slow-model")
        self.assertEqual(
            analyses[0].replies[0].hints,
            {
                "tags": {"any_of": ["hacker-news"]},
                "strings": {"contains": ["compact"], "equals": []},
            },
        )


class ConversationEvaluationClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_client_request_uses_glm51_none(self):
        case = conversation_evaluation_cases()[0]
        conversations = conversation_context(case.session_conversations)
        request = await baml_memory_search.ChooseMemorySearch__build_request_async(
            current_user_request=case.current_user_request,
            current_conversation=conversations[0] if conversations else None,
            session_memories=memory_context(case.session_memories),
            selected_task=selected_task_context(case.selected_task),
            conversation_evaluation_memories=conversation_evaluation_memory_context(
                case.conversation_evaluation_memories
            ),
            machine_state=local_machine_state_context("test"),
        )
        body = json.loads(request.body)

        self.assertEqual(body["model"], "glm-5.1")
        self.assertEqual(body["reasoning_effort"], "none")


def _provider(provider_id: str, surface: str):
    now = datetime.now(timezone.utc)
    return MemoryNode(
        id=provider_id,
        tags=(),
        timestamps=MemoryTimestamps(
            created_at=now,
            updated_at=now,
            read_at=None,
        ),
        content=Provider(
            name=provider_id,
            description="Test provider",
            baml_surface=surface,
        ),
    )


if __name__ == "__main__":
    unittest.main()
