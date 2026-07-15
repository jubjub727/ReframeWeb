from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class TaskFailureFlowOwnershipTests(unittest.TestCase):
    def test_complete_fail_retry_path_is_visible_in_the_baml_turn_graph(self) -> None:
        source = (ROOT / "baml_src/ns_voice_turn/task_flow.baml").read_text()
        steps = (
            "//# Run complete voice turn",
            "//# Task selection",
            "//# Load context",
            "//# Choose task",
            "//# Plan memory search",
            "//# Set search depth",
            "//# Retrieve memories",
            "//# Select memory",
            "//# Compose handoff",
            "//# Task attempts",
            "//# Execute task",
            "//# Check completion",
            "//# Retry or reselect",
            "//# Retry task",
            "//# Select another task",
        )

        positions = [source.index(step) for step in steps]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("CheckTaskCompletion(", source)
        self.assertIn("ResolveTaskFailure(", source)
        self.assertIn("if (resolution.can_refine)", source)
        self.assertGreaterEqual(source.count("while (true)"), 2)

    def test_python_agent_turn_contains_no_agentic_loop_or_failure_branch(self) -> None:
        source = (ROOT / "src/reframe_agent_host/voice/agent_turn.py").read_text()
        tree = ast.parse(source)

        self.assertFalse(any(isinstance(node, (ast.For, ast.While)) for node in ast.walk(tree)))
        self.assertEqual(source.count("run_voice_turn("), 1)
        for forbidden in (
            "CompletionResult.FAIL",
            "can_refine",
            "ResolveTaskFailure",
            "retry_context",
            "retry_prompt",
        ):
            self.assertNotIn(forbidden, source)

    def test_python_host_boundary_contains_no_retry_decision(self) -> None:
        source = (ROOT / "src/reframe_agent_host/voice/task_flow_host.py").read_text()
        for forbidden in (
            "CompletionResult.FAIL",
            "can_refine",
            "ResolveTaskFailure",
            "retry_context",
            "retry_prompt",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
