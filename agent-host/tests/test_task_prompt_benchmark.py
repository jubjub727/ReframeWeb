import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from reframe_agent_host import cli
from reframe_agent_host.baml_client import types
from reframe_agent_host.benchmarks.reasoning_efforts import (
    OPENCODE_GO_REASONING_EFFORT_CANDIDATES,
)
from reframe_agent_host.benchmarks.task_prompt_cases import task_prompt_cases
from reframe_agent_host.benchmarks.task_prompt_config import (
    TaskPromptBenchmarkConfig,
)
from reframe_agent_host.benchmarks.task_prompt_execution import (
    TaskPromptSnapshot,
    evaluate_task_prompt,
    snapshot_payload,
)
from reframe_agent_host.benchmarks.task_prompt_runner import (
    _select_cases,
    run_task_prompt_benchmark,
)
from reframe_agent_host.commands.parser import build_parser
from reframe_memory import MemoryNode, MemoryTimestamps, Provider


class FakeModel:
    def __init__(self, **values):
        self.__dict__.update(values)

    def model_dump(self, mode="json"):
        return dict(self.__dict__)


class TaskPromptBenchmarkTests(unittest.TestCase):
    def test_defaults_probe_all_reasoning_efforts(self):
        config = TaskPromptBenchmarkConfig(
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

    def test_select_cases_uses_task_prompt_cases(self):
        cases = _select_cases(task_prompt_cases(), ("stripe_followup_cleanup",))

        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].id, "stripe_followup_cleanup")
        self.assertEqual(
            cases[0].expected_task_name,
            "Request more information from the user",
        )

    def test_parser_accepts_task_prompt_benchmark(self):
        args = build_parser().parse_args(
            [
                "benchmark-task-prompt",
                "--runs",
                "2",
                "--case-id",
                "unsupported_visual_panel",
                "--provider-id",
                "memory_node:provider",
                "--reasoning-effort-candidate",
                "none",
                "--refresh-snapshots",
            ]
        )

        self.assertEqual(args.command, "benchmark-task-prompt")
        self.assertEqual(args.runs, 2)
        self.assertEqual(args.case_ids, ["unsupported_visual_panel"])
        self.assertEqual(args.provider_ids, ["memory_node:provider"])
        self.assertEqual(args.reasoning_effort_candidates, ["none"])
        self.assertTrue(args.refresh_snapshots)

    def test_cli_dispatches_task_prompt_benchmark(self):
        captured = {}

        async def fake_run_benchmark_task_prompt(**kwargs):
            captured.update(kwargs)
            return 0

        with patch.object(
            cli,
            "run_benchmark_task_prompt",
            fake_run_benchmark_task_prompt,
        ):
            with self.assertRaises(SystemExit) as raised:
                cli.main(
                    [
                        "benchmark-task-prompt",
                        "--reasoning-effort-candidate",
                        "none",
                    ]
                )

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(captured["reasoning_effort_candidates"], ["none"])
        self.assertIsNone(captured["reasoning_efforts"])
        self.assertFalse(captured["refresh_snapshots"])

    def test_evaluation_scores_shape_and_non_empty_sections(self):
        snapshot = _snapshot()
        decision = types.TaskPromptDecision(
            full_task_prompt=(
                "Task:\n"
                "Ask for the information needed to continue.\n\n"
                "Input:\n"
                "Use selected_task memory_node:core_task_request_info and ask "
                "about the spreadsheet."
            )
        )

        evaluation = evaluate_task_prompt(decision, snapshot)

        self.assertTrue(evaluation["correct"])
        self.assertTrue(evaluation["structural_pass"])
        self.assertTrue(evaluation["shape_ok"])
        self.assertTrue(evaluation["task_present"])
        self.assertTrue(evaluation["input_present"])

    def test_evaluation_requires_non_empty_input(self):
        snapshot = _snapshot()
        decision = types.TaskPromptDecision(
            full_task_prompt=(
                "Task:\n"
                "Ask only for the information needed to continue.\n\n"
                "Input:\n"
            )
        )

        evaluation = evaluate_task_prompt(decision, snapshot)

        self.assertFalse(evaluation["correct"])
        self.assertFalse(evaluation["input_present"])

    def test_snapshot_payload_saves_task_prompt_input(self):
        payload = snapshot_payload(_snapshot())

        self.assertEqual(payload["case_id"], "stripe_followup_cleanup")
        self.assertIn("task_prompt_input_snapshot", payload)
        self.assertEqual(
            payload["task_prompt_input_snapshot"]["selected_task"]["prompt"],
            "Ask only for the information needed to continue.",
        )
        self.assertEqual(
            payload["task_prompt_input_snapshot"]["relevance_decision"][
                "kept_memory_ids"
            ],
            ["memory_node:stripe_memory"],
        )
        self.assertNotIn("expected_input_phrases", payload)
        self.assertNotIn("forbidden_phrases", payload)


class TaskPromptRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_runner_reuses_one_snapshot_for_each_provider_effort(self):
        case = task_prompt_cases()[0]
        providers = (
            _provider("provider:one", "OpenCodeGoModelGlm51"),
            _provider("provider:two", "OpenCodeGoModelKimiK25"),
        )
        built_snapshots = []
        benchmark_calls = []

        async def fake_direct_model_providers(database, provider_ids):
            self.assertEqual(provider_ids, ())
            return providers

        async def fake_build_task_prompt_snapshot(database, build_case, refresh=False):
            self.assertEqual(build_case, case)
            self.assertFalse(refresh)
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
                "task_prompt_input_snapshot": {
                    "selected_memories": ["reused-context"],
                },
            }

        config = TaskPromptBenchmarkConfig(
            runs=1,
            warmup_runs=0,
            delay_seconds=0,
            provider_cooldown_seconds=0,
            case_ids=(case.id,),
        )

        with patch(
            "reframe_agent_host.benchmarks.task_prompt_runner.task_prompt_cases",
            lambda: (case,),
        ):
            with patch(
                "reframe_agent_host.benchmarks.task_prompt_runner.direct_model_providers",
                fake_direct_model_providers,
            ):
                with patch(
                    "reframe_agent_host.benchmarks.task_prompt_runner.build_task_prompt_snapshot",
                    fake_build_task_prompt_snapshot,
                ):
                    with patch(
                        "reframe_agent_host.benchmarks.task_prompt_runner.discover_task_prompt_reasoning_efforts",
                        fake_discover,
                    ):
                        with patch(
                            "reframe_agent_host.benchmarks.task_prompt_runner.benchmark_task_prompt_provider",
                            fake_benchmark,
                        ):
                            with patch(
                                "reframe_agent_host.benchmarks.task_prompt_runner.snapshot_payload",
                                fake_snapshot_payload,
                            ):
                                result = await run_task_prompt_benchmark(
                                    database=FakeModel(),
                                    config=config,
                                )

        self.assertEqual(len(built_snapshots), 1)
        self.assertEqual(len(benchmark_calls), 4)
        for _provider_id, _effort, snapshots in benchmark_calls:
            self.assertEqual(snapshots, tuple(built_snapshots))
            self.assertIs(snapshots[0], built_snapshots[0])
        self.assertEqual(
            result["snapshots"][0]["task_prompt_input_snapshot"][
                "selected_memories"
            ],
            ["reused-context"],
        )
        self.assertEqual(result["summary"]["base_providers"], 2)
        self.assertEqual(result["summary"]["provider_effort_runs"], 4)


def _snapshot():
    case = _stripe_case()
    selected_task = types.SelectedTaskContext(
        id="memory_node:core_task_request_info",
        name="Request more information from the user",
        description="Use when the request needs input before it can be handled.",
        input="The user's request.",
        output="Ask for the information needed to continue.",
        prompt="Ask only for the information needed to continue.",
        provider_id="memory_node:core_provider",
        created_at="2026-07-05T00:00:00+00:00",
        updated_at="2026-07-05T00:00:00+00:00",
        read_at="NONE",
    )
    task_choice = types.TaskChoiceDecision(
        selected_task_id=selected_task.id,
        confidence=1.0,
        reason="test",
    )
    return TaskPromptSnapshot(
        case=case,
        current_timestamp="2026-07-05T00:00:00+00:00",
        session_id="memory_node:session",
        conversation_id="memory_node:conversation",
        task_choice=task_choice,
        selected_task=selected_task,
        session_conversations=[],
        session_memories=[],
        memory_search_hints=None,
        search_depths=None,
        retrieved_memories=None,
        relevance_decision=types.RelevantMemoryDecision(
            kept_memory_ids=["memory_node:stripe_memory"]
        ),
        selected_memories=None,
        selected_memory_contexts=[],
        task_prompt_memories=[],
        latency_seconds=0.1,
        stage_latency_seconds={},
    )


def _stripe_case():
    for case in task_prompt_cases():
        if case.id == "stripe_followup_cleanup":
            return case
    raise AssertionError("stripe_followup_cleanup case missing")


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
