import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from reframe_agent_host import cli
from reframe_agent_host.benchmarks.control_flow_cases import control_flow_cases
from reframe_agent_host.benchmarks.control_flow_context import (
    case_conversation_context,
    case_session_memory_context,
)
from reframe_agent_host.benchmarks.control_flow_execution import ControlFlowSnapshot
from reframe_agent_host.benchmarks.memory_relevance_config import (
    MemoryRelevanceBenchmarkConfig,
)
from reframe_agent_host.benchmarks.memory_relevance_execution import (
    MemoryRelevanceSnapshot,
    snapshot_payload,
)
from reframe_agent_host.benchmarks.memory_relevance_runner import (
    _select_cases,
    run_memory_relevance_benchmark,
)
from reframe_agent_host.benchmarks.reasoning_efforts import (
    OPENCODE_GO_REASONING_EFFORT_CANDIDATES,
)
from reframe_agent_host.commands.parser import build_parser
from reframe_memory import MemoryNode, MemoryTimestamps, Provider


class FakeModel:
    def __init__(self, **values):
        self.__dict__.update(values)

    def model_dump(self, mode="json"):
        return dict(self.__dict__)


class MemoryRelevanceBenchmarkTests(unittest.TestCase):
    def test_defaults_probe_all_reasoning_efforts(self):
        config = MemoryRelevanceBenchmarkConfig(
            runs=1,
            warmup_runs=0,
            delay_seconds=0,
            provider_cooldown_seconds=0,
        )

        self.assertEqual(config.reasoning_efforts, ())
        self.assertEqual(
            config.reasoning_effort_candidates,
            OPENCODE_GO_REASONING_EFFORT_CANDIDATES,
        )
        self.assertIn("none", config.reasoning_effort_candidates)
        self.assertIn("xhigh", config.reasoning_effort_candidates)
        self.assertIn("max", config.reasoning_effort_candidates)

    def test_select_cases_uses_real_control_flow_cases(self):
        cases = _select_cases(control_flow_cases(), ("hacker_news_compact_panel",))

        self.assertEqual(len(cases), 1)
        case = cases[0]
        self.assertEqual(case.id, "hacker_news_compact_panel")
        self.assertTrue(case.session.conversations)
        self.assertTrue(case.session.memories)
        self.assertIn(
            "Hacker News worked best",
            case.session.conversations[0].messages[0].content,
        )

    def test_parser_accepts_memory_relevance_benchmark(self):
        args = build_parser().parse_args(
            [
                "benchmark-memory-relevance",
                "--runs",
                "2",
                "--case-id",
                "hacker_news_compact_panel",
                "--provider-id",
                "memory_node:provider",
                "--reasoning-effort-candidate",
                "none",
            ]
        )

        self.assertEqual(args.command, "benchmark-memory-relevance")
        self.assertEqual(args.runs, 2)
        self.assertEqual(args.case_ids, ["hacker_news_compact_panel"])
        self.assertEqual(args.provider_ids, ["memory_node:provider"])
        self.assertEqual(args.reasoning_effort_candidates, ["none"])

    def test_cli_dispatches_memory_relevance_benchmark(self):
        captured = {}

        async def fake_run_benchmark_memory_relevance(**kwargs):
            captured.update(kwargs)
            return 0

        with patch.object(
            cli,
            "run_benchmark_memory_relevance",
            fake_run_benchmark_memory_relevance,
        ):
            with self.assertRaises(SystemExit) as raised:
                cli.main(
                    [
                        "benchmark-memory-relevance",
                        "--reasoning-effort-candidate",
                        "none",
                    ]
                )

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(captured["reasoning_effort_candidates"], ["none"])
        self.assertIsNone(captured["reasoning_efforts"])

    def test_snapshot_payload_saves_reusable_relevance_input(self):
        case = control_flow_cases()[0]
        control = ControlFlowSnapshot(
            case=case,
            task_choice=FakeModel(selected_task_id=case.expected_task_id),
            selected_task=FakeModel(id=case.expected_task_id),
            search_hints=FakeModel(search_terms=["compact"]),
            session_conversations=case_conversation_context(case),
            session_memories=case_session_memory_context(case),
            search_domains=[],
            search_depth_memories=[],
            latency_seconds=1.5,
            stage_latency_seconds={"task_choice": 1.0, "search_hints": 0.5},
        )
        snapshot = MemoryRelevanceSnapshot(
            case=case,
            control_flow=control,
            search_depths=FakeModel(depths={}),
            retrieved_memories=None,
            candidate_memories=[
                FakeModel(
                    id="memory_node:benchmark_session_memory",
                    description="Use compact rows.",
                )
            ],
            expected_kept_memory_ids=("memory_node:benchmark_session_memory",),
            relevance_memories=[],
            latency_seconds=2.0,
            stage_latency_seconds={
                "task_choice": 1.0,
                "search_hints": 0.5,
                "search_depth": 0.25,
                "memory_retrieval": 0.25,
            },
        )

        payload = snapshot_payload(snapshot)
        relevance_input = payload["relevance_input_snapshot"]

        self.assertEqual(payload["case_id"], case.id)
        self.assertTrue(payload["task_correct"])
        self.assertIn("candidate_memories", relevance_input)
        self.assertIn(
            "Hacker News worked best",
            relevance_input["current_conversation"]["messages"][0]["content"],
        )
        self.assertEqual(
            relevance_input["candidate_memories"][0]["id"],
            "memory_node:benchmark_session_memory",
        )


class MemoryRelevanceRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_runner_reuses_one_snapshot_for_each_provider_effort(self):
        case = control_flow_cases()[0]
        providers = (
            _provider("provider:one", "OpenCodeGoModelGlm51"),
            _provider("provider:two", "OpenCodeGoModelKimiK25"),
        )
        built_snapshots = []
        benchmark_calls = []

        async def fake_direct_model_providers(database, provider_ids):
            self.assertEqual(provider_ids, ())
            return providers

        async def fake_build_memory_relevance_snapshot(build_case):
            self.assertEqual(build_case, case)
            snapshot = FakeModel(
                case=build_case,
                error=None,
                task_correct=True,
                latency_seconds=0.1,
                stage_latency_seconds={},
            )
            built_snapshots.append(snapshot)
            return snapshot

        async def fake_discover(provider, snapshots, config):
            self.assertEqual(snapshots, tuple(built_snapshots))
            return ("none", "low"), []

        async def fake_benchmark(provider, snapshots, config, effort):
            benchmark_calls.append((provider.id, effort, snapshots))
            return {
                "provider_id": provider.id,
                "total": 1,
                "correct": 1,
                "errors": 0,
                "case_results": [{"latency_seconds": 0.01}],
            }

        def fake_snapshot_payload(snapshot):
            return {
                "case_id": snapshot.case.id,
                "relevance_input_snapshot": {
                    "candidate_memories": ["reused-context"],
                },
            }

        config = MemoryRelevanceBenchmarkConfig(
            runs=1,
            warmup_runs=0,
            delay_seconds=0,
            provider_cooldown_seconds=0,
            case_ids=(case.id,),
        )

        with patch(
            "reframe_agent_host.benchmarks.memory_relevance_runner.control_flow_cases",
            lambda: (case,),
        ):
            with patch(
                "reframe_agent_host.benchmarks.memory_relevance_runner.direct_model_providers",
                fake_direct_model_providers,
            ):
                with patch(
                    "reframe_agent_host.benchmarks.memory_relevance_runner.build_memory_relevance_snapshot",
                    fake_build_memory_relevance_snapshot,
                ):
                    with patch(
                        "reframe_agent_host.benchmarks.memory_relevance_runner.discover_memory_relevance_reasoning_efforts",
                        fake_discover,
                    ):
                        with patch(
                            "reframe_agent_host.benchmarks.memory_relevance_runner.benchmark_memory_relevance_provider",
                            fake_benchmark,
                        ):
                            with patch(
                                "reframe_agent_host.benchmarks.memory_relevance_runner.snapshot_payload",
                                fake_snapshot_payload,
                            ):
                                result = await run_memory_relevance_benchmark(
                                    database=FakeModel(),
                                    config=config,
                                )

        self.assertEqual(len(built_snapshots), 1)
        self.assertEqual(len(benchmark_calls), 4)
        for _provider_id, _effort, snapshots in benchmark_calls:
            self.assertEqual(snapshots, tuple(built_snapshots))
            self.assertIs(snapshots[0], built_snapshots[0])
        self.assertEqual(
            result["snapshots"][0]["relevance_input_snapshot"][
                "candidate_memories"
            ],
            ["reused-context"],
        )
        self.assertEqual(result["summary"]["base_providers"], 2)
        self.assertEqual(result["summary"]["provider_effort_runs"], 4)


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
