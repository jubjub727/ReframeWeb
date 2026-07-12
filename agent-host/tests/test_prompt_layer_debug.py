from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from baml_sdk.task_routing import TaskChoiceDecision
from reframe_agent_host.agent_flow.prompt_layer_debug import (
    PromptLayerDebugSession,
)


class PromptLayerDebugSessionTests(unittest.TestCase):
    def test_writes_inputs_result_request_and_index_without_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch(
                "reframe_agent_host.agent_flow.prompt_layer_debug._dump_dir",
                return_value=Path(temp_dir),
            ):
                session = PromptLayerDebugSession.begin(
                    current_user_request="Tell me a joke.",
                )
                self.assertIsNotNone(session)
                assert session is not None

                session.write_layer(
                    order=1,
                    name="choose_task",
                    inputs={"current_user_request": "Tell me a joke."},
                    result=TaskChoiceDecision(
                        selected_task_id="task:reply",
                        confidence=1.0,
                        candidate_memory=None,
                    ),
                    request=_Request(
                        body=json.dumps(
                            {
                                "model": "kimi-k2.5",
                                "messages": [
                                    {
                                        "role": "user",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "Choose a task.",
                                            },
                                        ],
                                    },
                                ],
                            },
                        ),
                        headers={"authorization": "Bearer secret"},
                    ),
                    elapsed_seconds=0.25,
                )

                layer = json.loads(
                    (Path(temp_dir) / "latest" / "01-choose_task.json").read_text(
                        encoding="utf-8",
                    ),
                )
                index = json.loads(
                    (Path(temp_dir) / "latest" / "index.json").read_text(
                        encoding="utf-8",
                    ),
                )

        self.assertEqual(layer["inputs"]["current_user_request"], "Tell me a joke.")
        self.assertEqual(layer["result"]["selected_task_id"], "task:reply")
        self.assertEqual(layer["request"]["summary"]["model"], "kimi-k2.5")
        self.assertEqual(layer["request"]["summary"]["messages"][0]["content_chars"], 14)
        self.assertEqual(index["layers"][0]["layer"], "choose_task")
        self.assertNotIn("headers", json.dumps(layer).lower())
        self.assertNotIn("secret", json.dumps(layer).lower())

    def test_dump_can_be_disabled(self) -> None:
        with mock.patch.dict(os.environ, {"REFRAME_PROMPT_LAYER_DUMP": "0"}):
            session = PromptLayerDebugSession.begin(
                current_user_request="Tell me a joke.",
            )

        self.assertIsNone(session)

    def test_latest_cleanup_failure_is_non_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            latest = root / "latest"
            latest.mkdir()
            (latest / "stale.json").write_text("{}", encoding="utf-8")
            with mock.patch(
                "reframe_agent_host.agent_flow.prompt_layer_debug._dump_dir",
                return_value=root,
            ):
                with mock.patch.object(Path, "unlink", side_effect=OSError(22)):
                    session = PromptLayerDebugSession.begin(
                        current_user_request="Tell me a joke.",
                    )

        self.assertIsNotNone(session)

    def test_latest_layer_write_failure_is_non_fatal(self) -> None:
        original_write_text = Path.write_text

        def write_text(path, text, *args, **kwargs):
            if path.parent.name == "latest":
                raise OSError(22, "Invalid argument", str(path))
            return original_write_text(path, text, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch(
                "reframe_agent_host.agent_flow.prompt_layer_debug._dump_dir",
                return_value=Path(temp_dir),
            ):
                session = PromptLayerDebugSession.begin(
                    current_user_request="Tell me a joke.",
                )
                self.assertIsNotNone(session)
                assert session is not None
                with mock.patch.object(Path, "write_text", autospec=True) as patched:
                    patched.side_effect = write_text
                    session.write_layer(
                        order=1,
                        name="choose_task",
                        inputs={"current_user_request": "Tell me a joke."},
                        result=None,
                        elapsed_seconds=0.1,
                    )

                self.assertTrue((session.run_dir / "01-choose_task.json").exists())


class _Request:
    def __init__(self, *, body: str, headers: dict[str, str]) -> None:
        self.body = body
        self.headers = headers


if __name__ == "__main__":
    unittest.main()
