from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from baml_sdk import task as baml_task
from baml_sdk import voice_turn as baml_voice_turn
from reframe_agent_host.agent_flow.prompt_layer_debug import PromptLayerDebugSession
from reframe_agent_host.agent_flow.task_review_debug import dump_task_reviews


class TaskReviewDebugTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_attempt_and_retry_write_separate_layers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch(
                "reframe_agent_host.agent_flow.prompt_layer_debug._dump_dir",
                return_value=Path(temp_dir),
            ):
                debug = PromptLayerDebugSession.begin(current_user_request="Do it")
                result = _result()
                with mock.patch(
                    "reframe_agent_host.agent_flow.task_review_debug."
                    "baml_task.CheckTaskCompletion__build_request_async",
                    side_effect=lambda **_kwargs: _Request("completion"),
                ):
                    with mock.patch(
                        "reframe_agent_host.agent_flow.task_review_debug."
                        "baml_task.WriteValidationReply__build_request_async",
                        side_effect=lambda **_kwargs: _Request("refusal"),
                    ):
                        await dump_task_reviews(debug, result)

            latest = Path(temp_dir) / "latest"
            names = sorted(path.name for path in latest.glob("*.json"))
            refusal = json.loads(
                (latest / "10-write_validation_reply.json").read_text()
            )

        self.assertEqual(
            names,
            [
                "09-check_task_completion.json",
                "10-write_validation_reply.json",
                "11-check_task_completion.json",
                "index.json",
            ],
        )
        self.assertEqual(
            refusal["inputs"]["earlier_refusal_reply_text"],
            "- First correction",
        )
        self.assertTrue(refusal["result"]["can_refine"])


class _Request:
    def __init__(self, label: str) -> None:
        self.body = json.dumps({"model": "debug", "messages": [label]})


def _result():
    decision = baml_task.TaskFailureDecision(
        validation_reply="Second correction",
        can_refine=True,
    )
    return mock.Mock(
        completion_reviews=[
            baml_voice_turn.VoiceTaskCompletionReview(
                attempt_id="attempt-1",
                completion_string="Finished",
                output_summary="Incomplete",
                completion=baml_task.CompletionResult.FAIL,
                elapsed_ms=75,
            ),
            baml_voice_turn.VoiceTaskCompletionReview(
                attempt_id="attempt-2",
                completion_string="Finished",
                output_summary="Complete",
                completion=baml_task.CompletionResult.PASS,
                elapsed_ms=80,
            ),
        ],
        failure_reviews=[
            baml_voice_turn.VoiceTaskFailureReview(
                attempt_id="attempt-1",
                task_prompt="Task",
                completion_string="Finished",
                output_summary="Incomplete",
                earlier_refusal_reply_text="- First correction",
                decision=decision,
                elapsed_ms=90,
            ),
        ],
    )


if __name__ == "__main__":
    unittest.main()
