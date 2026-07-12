import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from baml_sdk import benchmarks as baml_benchmarks
from reframe_agent_host import cli
from reframe_agent_host.benchmarks.config import (
    ControlFlowBenchmarkConfig,
    SEARCH_DEPTH_DEFAULT_MODEL_ID,
)
from reframe_agent_host.benchmarks.control_flow_execution import (
    ControlFlowSnapshot,
    snapshot_payload,
)
from reframe_agent_host.benchmarks.runner import _search_depth_providers
from reframe_agent_host.benchmarks.control_flow_time import cutoff_age, format_duration
from reframe_agent_host.commands.control_flow_report import print_control_flow_report
from reframe_agent_host.commands.parser import build_parser
from benchmark_fixtures import FakeModel, provider as _provider


class ControlFlowBenchmarkTests(unittest.TestCase):
    def test_duration_format_uses_readable_units(self):
        self.assertEqual(format_duration(30 * 60), "30 minutes")
        self.assertEqual(format_duration(90 * 60), "1 hour and 30 minutes")
        self.assertEqual(
            format_duration(((2 * 24 + 1) * 60 + 30) * 60),
            "2 days 1 hour and 30 minutes",
        )

    def test_cutoff_age_reports_display_and_seconds(self):
        age = cutoff_age(
            "2026-07-03T15:00:00Z",
            "2026-07-03T13:30:00Z",
        )

        self.assertEqual(age["seconds"], 90 * 60)
        self.assertEqual(age["display"], "1 hour and 30 minutes")

    def test_cases_use_session_shaped_memory_graph(self):
        case = baml_benchmarks.ControlFlowCases()[0]

        self.assertTrue(case.session.id.startswith("benchmark_session:"))
        self.assertGreaterEqual(len(case.session.conversations), 1)
        self.assertGreaterEqual(len(case.session.memories), 1)
        self.assertEqual(case.session.read_at, "NONE")
        self.assertLessEqual(
            case.session.created_at,
            case.session.conversations[0].created_at,
        )

    def test_parser_accepts_control_flow_benchmark(self):
        args = build_parser().parse_args(
            [
                "benchmark-control-flow",
                "--runs",
                "2",
                "--case-id",
                "reddit_slow_scroll",
                "--search-depth-model-id",
                "deepseek-v4-flash",
                "--reasoning-effort",
                "low",
                "--reasoning-effort-candidate",
                "high",
            ]
        )

        self.assertEqual(args.command, "benchmark-control-flow")
        self.assertEqual(args.runs, 2)
        self.assertEqual(args.case_ids, ["reddit_slow_scroll"])
        self.assertEqual(args.search_depth_model_id, "deepseek-v4-flash")
        self.assertEqual(args.reasoning_efforts, ["low"])
        self.assertEqual(args.reasoning_effort_candidates, ["high"])

    def test_control_flow_defaults_to_chosen_search_depth_model(self):
        providers = (
            _provider("provider:deepseek", "opencode_go.OpenCodeGoModelDeepseekV4Flash"),
            _provider("provider:glm51", "opencode_go.OpenCodeGoModelGlm51"),
        )
        config = ControlFlowBenchmarkConfig(
            runs=1,
            warmup_runs=0,
            delay_seconds=0,
            provider_cooldown_seconds=0,
        )

        selected = _search_depth_providers(providers, config)

        self.assertEqual(SEARCH_DEPTH_DEFAULT_MODEL_ID, "glm-5.1")
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].content.baml_surface, "opencode_go.OpenCodeGoModelGlm51")

    def test_control_flow_can_select_a_different_search_depth_model(self):
        providers = (
            _provider("provider:deepseek", "opencode_go.OpenCodeGoModelDeepseekV4Flash"),
            _provider("provider:glm51", "opencode_go.OpenCodeGoModelGlm51"),
        )
        config = ControlFlowBenchmarkConfig(
            runs=1,
            warmup_runs=0,
            delay_seconds=0,
            provider_cooldown_seconds=0,
            search_depth_model_id="deepseek-v4-flash",
        )

        selected = _search_depth_providers(providers, config)

        self.assertEqual(len(selected), 1)
        self.assertEqual(
            selected[0].content.baml_surface,
            "opencode_go.OpenCodeGoModelDeepseekV4Flash",
        )

    def test_cli_passes_search_depth_model_to_control_flow_command(self):
        captured = {}

        async def fake_run_benchmark_control_flow(**kwargs):
            captured.update(kwargs)
            return 0

        with patch.object(
            cli,
            "run_benchmark_control_flow",
            fake_run_benchmark_control_flow,
        ):
            with self.assertRaises(SystemExit) as raised:
                cli.main(
                    [
                        "benchmark-control-flow",
                        "--search-depth-model-id",
                        "deepseek-v4-flash",
                        "--reasoning-effort-candidate",
                        "low",
                    ]
                )

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(captured["search_depth_model_id"], "deepseek-v4-flash")
        self.assertEqual(captured["reasoning_effort_candidates"], ["low"])

    def test_snapshot_payload_saves_search_depth_input(self):
        case = baml_benchmarks.ControlFlowCases()[0]
        snapshot = ControlFlowSnapshot(
            case=case,
            task_choice=FakeModel(selected_task_id=case.expected_task_id),
            selected_task=FakeModel(id=case.expected_task_id),
            search_hints=FakeModel(search_terms=["scroll speed"]),
            session_conversations=[],
            session_memories=[],
            search_domains=[],
            search_depth_memories=[],
            latency_seconds=1.5,
            stage_latency_seconds={"task_choice": 1.0, "search_hints": 0.5},
        )

        payload = snapshot_payload(snapshot)

        self.assertEqual(payload["case_id"], case.id)
        self.assertTrue(payload["task_correct"])
        self.assertIn("search_depth_input_snapshot", payload)
        self.assertEqual(
            payload["search_depth_input_snapshot"]["session"]["id"],
            case.session.id,
        )

    def test_report_displays_search_depth_ages(self):
        result = {
            "summary": {
                "providers": 1,
                "cases": 1,
                "snapshots": 1,
                "snapshot_errors": 0,
                "total": 1,
                "correct": 1,
            },
            "snapshots": [
                {
                    "case_id": "sample",
                    "latency_seconds": 1.5,
                    "stage_latency_seconds": {
                        "task_choice": 1.0,
                        "search_hints": 0.5,
                    },
                    "selected_task_id": "task:sample",
                    "task_correct": True,
                }
            ],
            "providers": [
                {
                    "model_id": "test-model",
                    "latency_seconds": {"average": 1.2, "best": 1.2, "worst": 1.2},
                    "stage_latency_seconds": {
                        "search_depth": {
                            "average": 1.2,
                            "best": 1.2,
                            "worst": 1.2,
                        }
                    },
                    "case_results": [
                        {
                            "case_id": "sample",
                            "run_index": 0,
                            "latency_seconds": 1.2,
                            "selected_task_id": "task:sample",
                            "task_correct": True,
                            "search_depth_ages": {
                                "past_conversation_context": {
                                    "created_after": {
                                        "seconds": 5400,
                                        "display": "1 hour and 30 minutes",
                                    }
                                }
                            },
                        }
                    ],
                }
            ],
        }
        output = StringIO()

        with redirect_stdout(output):
            print_control_flow_report(result)

        self.assertIn("past_conversation_context", output.getvalue())
        self.assertIn("1 hour and 30 minutes", output.getvalue())
        self.assertIn("snapshots:", output.getvalue())
        self.assertIn("depth=1.200 s", output.getvalue())


if __name__ == "__main__":
    unittest.main()
