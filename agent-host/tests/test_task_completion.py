from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import baml_sdk as types
from reframe_agent_host.agent_flow.prompt_layer_debug import (
    PromptLayerDebugSession,
)
from reframe_agent_host.agent_flow.task_completion import TaskCompletionChecker


class TaskCompletionCheckerTests(unittest.IsolatedAsyncioTestCase):
    async def test_completion_checker_writes_prompt_layer_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with mock.patch(
                "reframe_agent_host.agent_flow.prompt_layer_debug._dump_dir",
                return_value=root / "prompt-layers",
            ):
                with mock.patch(
                    "reframe_agent_host.agent_flow.task_completion.baml."
                    "CheckTaskCompletion__build_request_async",
                    return_value=_Request(
                        body=json.dumps(
                            {
                                "model": "glm-5.1",
                                "reasoning_effort": "none",
                                "messages": [
                                    {
                                        "role": "user",
                                        "content": "Completion prompt",
                                    },
                                ],
                            },
                        ),
                        headers={},
                    ),
                ):
                    with mock.patch(
                        "reframe_agent_host.agent_flow.task_completion.baml."
                        "CheckTaskCompletion_async",
                        return_value=types.CompletionResult.PASS,
                    ):
                        prompt_debug = PromptLayerDebugSession.begin(
                            current_user_request="Done?",
                        )
                        assert prompt_debug is not None
                        result = await TaskCompletionChecker().check(
                            completion_string="A reply was sent.",
                            output_summary="The recorded actions sent a reply.",
                            prompt_layer_debug=prompt_debug,
                        )

            layer = json.loads(
                (
                    root
                    / "prompt-layers"
                    / "latest"
                    / "09-check_task_completion.json"
                ).read_text(encoding="utf-8"),
            )

        self.assertEqual(result, types.CompletionResult.PASS)
        self.assertEqual(layer["layer"], "check_task_completion")
        self.assertEqual(layer["result"], "PASS")
        self.assertEqual(layer["request"]["summary"]["model"], "glm-5.1")


class _Request:
    def __init__(self, *, body: str, headers: dict[str, str]) -> None:
        self.body = body
        self.headers = headers


if __name__ == "__main__":
    unittest.main()
