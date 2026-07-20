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
            "//# Run selected task",
            "//# Plan memory search",
            "//# Set search depth",
            "//# Retrieve memories",
            "//# Select memory",
            "//# Compose handoff",
            "//# Task attempts",
            "//# Execute task",
            "//# Check completion",
            "//# Complete task",
            "//# Retry or reselect",
            "//# Retry task",
            "//# Select another task",
        )

        positions = [source.index(step) for step in steps]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("CheckTaskCompletion(", source)
        self.assertIn("task_completion_conversation = TaskConversation(", source)
        self.assertIn("current_conversation = task_completion_conversation", source)
        self.assertIn("current_user_request = current_user_request", source)
        self.assertIn("if (task_complete)", source)
        self.assertIn("CheckRequestCompletion(", source)
        self.assertIn('if (selected_task.model_id == "magic:do-nothing")', source)
        self.assertIn("//# Check request completion", source)
        self.assertLess(
            source.index('if (selected_task.model_id == "magic:do-nothing")'),
            source.index("//# Plan memory search"),
        )
        self.assertIn("ResolveTaskFailure(", source)
        self.assertIn("if (resolution.can_refine)", source)
        self.assertGreaterEqual(source.count("while ("), 2)
        self.assertIn("while (!voice_request_complete)", source)
        self.assertEqual(source.count("ReviewMemories("), 1)
        self.assertIn("if (should_check)", source)
        self.assertEqual(source.count("if (request_complete)"), 1)
        self.assertIn("if (memories_selected)", source)
        self.assertNotIn("if (consecutive_no_action_count < 3)", source)
        self.assertNotIn("if (RequestIsComplete(", source)
        self.assertNotIn("if (root.memory.", source)
        self.assertIn("//# Return result", source)
        self.assertEqual(source.count("//# Check request completion"), 1)
        self.assertIn("//# Skip completion model", source)
        self.assertIn("//# Choose another task", source)
        self.assertIn("//# Finish without saving", source)

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
