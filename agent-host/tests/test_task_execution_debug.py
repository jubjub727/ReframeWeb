from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from baml_sdk.task import TaskExecutionResult, TaskReturnItem
from reframe_agent_host.agent_flow.prompt_layer_debug import (
    PromptLayerDebugSession,
)
from reframe_agent_host.agent_flow.task_execution import TaskExecutionPlanner
from reframe_agent_host.agent_flow.task_execution_debug import (
    TaskExecutionDebugDump,
)
from reframe_agent_host.magic_providers import (
    MAGIC_DO_NOTHING_BAML_SURFACE,
    MAGIC_DO_NOTHING_MODEL_ID,
)
from reframe_memory import MemoryNode, MemoryTimestamps, Provider, Task


class TaskExecutionDebugDumpTests(unittest.IsolatedAsyncioTestCase):
    def test_records_prompt_request_and_result_without_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch(
                "reframe_agent_host.agent_flow.task_execution_debug._dump_dir",
                return_value=Path(temp_dir),
            ):
                dump = TaskExecutionDebugDump.begin(
                    selected_task=_task_node(),
                    provider=_provider_node(),
                    client_name="opencode_go.OpenCodeGoModelDeepseekV4FlashReasoningMax",
                    full_task_prompt="Reply to the user.",
                )
                self.assertIsNotNone(dump)
                assert dump is not None

                dump.record_request(
                    _Request(
                        body=json.dumps(
                            {
                                "model": "deepseek-v4-flash",
                                "reasoning_effort": "max",
                                "messages": [
                                    {"role": "system", "content": "System"},
                                    {
                                        "role": "user",
                                        "content": [
                                            {"type": "text", "text": "User prompt"},
                                        ],
                                    },
                                ],
                            },
                        ),
                        headers={"authorization": "Bearer secret"},
                    ),
                )
                dump.record_result(
                    elapsed_seconds=1.25,
                    result=TaskExecutionResult(
                        returns=[
                            TaskReturnItem(
                                name="agent_reply",
                                payload={"text": "Hi"},
                            ),
                        ],
                    ),
                )

                metadata = json.loads(dump.latest_metadata_path.read_text())
                request_body = dump.latest_request_path.read_text()

        self.assertEqual(metadata["status"], "ok")
        self.assertEqual(metadata["prompt"]["chars"], 18)
        self.assertEqual(metadata["request"]["model"], "deepseek-v4-flash")
        self.assertEqual(metadata["request"]["reasoning_effort"], "max")
        self.assertEqual(metadata["request"]["messages"][1]["content_chars"], 11)
        self.assertEqual(metadata["result"]["return_names"], ["agent_reply"])
        self.assertIn("User prompt", request_body)
        self.assertIn("deepseek-v4-flash", request_body)
        self.assertNotIn("headers", json.dumps(metadata).lower())
        self.assertNotIn("secret", json.dumps(metadata).lower())
        self.assertNotIn("secret", request_body.lower())

    def test_dump_can_be_disabled(self) -> None:
        with mock.patch.dict(os.environ, {"REFRAME_TASK_EXECUTION_DUMP": "0"}):
            dump = TaskExecutionDebugDump.begin(
                selected_task=_task_node(),
                provider=_provider_node(),
                client_name="opencode_go.OpenCodeGoModelDeepseekV4FlashReasoningMax",
                full_task_prompt="Reply to the user.",
            )

        self.assertIsNone(dump)

    def test_latest_prompt_write_failure_is_non_fatal(self) -> None:
        original_write_text = Path.write_text

        def write_text(path, text, *args, **kwargs):
            if path.name == "latest.prompt.txt":
                raise OSError(22, "Invalid argument", str(path))
            return original_write_text(path, text, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch(
                "reframe_agent_host.agent_flow.task_execution_debug._dump_dir",
                return_value=Path(temp_dir),
            ):
                with mock.patch.object(Path, "write_text", autospec=True) as patched:
                    patched.side_effect = write_text
                    dump = TaskExecutionDebugDump.begin(
                        selected_task=_task_node(),
                        provider=_provider_node(),
                        client_name="opencode_go.OpenCodeGoModelGlm51ReasoningNone",
                        full_task_prompt="Reply to the user.",
                    )

                self.assertIsNotNone(dump)
                assert dump is not None
                self.assertTrue(dump.prompt_path.exists())

    async def test_task_execution_writes_prompt_layer_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with mock.patch(
                "reframe_agent_host.agent_flow.prompt_layer_debug._dump_dir",
                return_value=root / "prompt-layers",
            ):
                with mock.patch(
                    "reframe_agent_host.agent_flow.task_execution_debug._dump_dir",
                    return_value=root / "task-execution",
                ):
                    with mock.patch(
                        "reframe_agent_host.agent_flow.task_execution.baml_task."
                        "PerformTask__build_request_async",
                        return_value=_Request(
                            body=json.dumps(
                                {
                                    "model": "deepseek-v4-flash",
                                    "reasoning_effort": "max",
                                    "messages": [
                                        {
                                            "role": "user",
                                            "content": "Task prompt",
                                        },
                                    ],
                                },
                            ),
                            headers={},
                        ),
                    ):
                        with mock.patch(
                            "reframe_agent_host.agent_flow.task_execution.baml_task."
                            "PerformTask_async",
                            return_value=TaskExecutionResult(
                                returns=[
                                    TaskReturnItem(
                                        name="agent_reply",
                                        payload={"text": "Hi"},
                                    ),
                                ],
                            ),
                        ):
                            prompt_debug = PromptLayerDebugSession.begin(
                                current_user_request="Hi",
                            )
                            assert prompt_debug is not None
                            planner = TaskExecutionPlanner(
                                database=_FakeTaskExecutionDatabase(),
                            )
                            await planner.execute_task(
                                "memory_node:task",
                                "Task:\nReply.\n\nInput:\nHi",
                                prompt_layer_debug=prompt_debug,
                            )

                layer = json.loads(
                    (
                        root
                        / "prompt-layers"
                        / "latest"
                        / "07-perform_task.json"
                    ).read_text(encoding="utf-8"),
                )

        self.assertEqual(layer["layer"], "perform_task")
        self.assertEqual(layer["result"]["returns"][0]["name"], "agent_reply")
        self.assertEqual(layer["request"]["summary"]["reasoning_effort"], "max")

    async def test_magic_do_nothing_provider_returns_empty_without_baml_call(self) -> None:
        planner = TaskExecutionPlanner(
            database=_FakeTaskExecutionDatabase(
                task=_do_nothing_task_node(),
                provider=_magic_provider_node(),
            ),
        )

        with mock.patch(
            "reframe_agent_host.agent_flow.task_execution.baml_task."
            "PerformTask__build_request_async",
        ) as build_request:
            with mock.patch(
                "reframe_agent_host.agent_flow.task_execution.baml_task.PerformTask_async",
            ) as perform_task:
                result = await planner.execute_task(
                    "memory_node:do_nothing_task",
                    "Task:\nDo nothing.\n\nInput:\n...",
                )

        self.assertEqual(result.returns, [])
        build_request.assert_not_called()
        perform_task.assert_not_called()


class _Request:
    def __init__(self, *, body: str, headers: dict[str, str]) -> None:
        self.body = body
        self.headers = headers


class _FakeTaskExecutionDatabase:
    def __init__(self, *, task=None, provider=None) -> None:
        self.tasks = _FakeTasks(task or _task_node())
        self.providers = _FakeProviders(provider or _provider_node())


class _FakeTasks:
    def __init__(self, task) -> None:
        self._task = task

    async def get(self, _task_id: str):
        return self._task


class _FakeProviders:
    def __init__(self, provider) -> None:
        self._provider = provider

    async def get(self, _provider_id: str):
        return self._provider


def _task_node() -> MemoryNode[Task]:
    return MemoryNode(
        id="memory_node:task",
        tags=("reply",),
        timestamps=_timestamps(),
        content=Task(
            name="Reply to user",
            description="Reply.",
            input="The user's message.",
            output="agent_reply",
            prompt="Return agent_reply.",
            provider_id="memory_node:provider",
        ),
    )


def _provider_node() -> MemoryNode[Provider]:
    return MemoryNode(
        id="memory_node:provider",
        tags=("provider",),
        timestamps=_timestamps(),
        content=Provider(
            name="OpenCode Go direct model: deepseek-v4-flash / max",
            description="Provider.",
            baml_surface="opencode_go.OpenCodeGoModelDeepseekV4Flash",
            model_id="deepseek-v4-flash",
            reasoning_effort="max",
        ),
    )


def _do_nothing_task_node() -> MemoryNode[Task]:
    return MemoryNode(
        id="memory_node:do_nothing_task",
        tags=("nothing", "silent"),
        timestamps=_timestamps(),
        content=Task(
            name="Do nothing",
            description="Do nothing.",
            input="The user's request or conversational context.",
            output="",
            prompt="Do nothing. Return an empty returns array.\n",
            provider_id="memory_node:magic_provider",
        ),
    )


def _magic_provider_node() -> MemoryNode[Provider]:
    return MemoryNode(
        id="memory_node:magic_provider",
        tags=("magic-provider", "do-nothing", "silent"),
        timestamps=_timestamps(),
        content=Provider(
            name="Magic provider: do nothing",
            description="No-op provider.",
            baml_surface=MAGIC_DO_NOTHING_BAML_SURFACE,
            model_id=MAGIC_DO_NOTHING_MODEL_ID,
        ),
    )


def _timestamps() -> MemoryTimestamps:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return MemoryTimestamps(created_at=now, updated_at=now, read_at=None)


if __name__ == "__main__":
    unittest.main()
