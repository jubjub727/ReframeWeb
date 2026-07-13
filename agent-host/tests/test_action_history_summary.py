from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest import mock

from reframe_agent_host.agent_flow.action_history import ActionHistorySummarizer
from reframe_memory import MemoryNode, MemoryTimestamps, Provider, Task


class ActionHistorySummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_summary_uses_selected_task_provider_client(self) -> None:
        captured = {}

        async def summarize(**kwargs):
            captured.update(kwargs)
            return "The recorded actions replied to the user."

        with mock.patch(
            "reframe_agent_host.agent_flow.action_history.baml_task."
            "SummariseActionHistory_async",
            side_effect=summarize,
        ):
            result = await ActionHistorySummarizer(
                database=_FakeDatabase(),
            ).summarize(
                "memory_node:task_history",
                selected_task_id="memory_node:task",
            )

        self.assertEqual(result, "The recorded actions replied to the user.")
        self.assertEqual(
            captured["client"].name,
            "OpenCodeGoModelGlm51ReasoningNone",
        )


class _FakeDatabase:
    def __init__(self) -> None:
        self.task_history = _FakeTaskHistory()
        self.tasks = _FakeTasks()
        self.providers = _FakeProviders()


class _FakeTaskHistory:
    async def render(self, _task_history_id: str) -> str:
        return "- Session: memory_node:session\n  Conversation: memory_node:conversation"


class _FakeTasks:
    async def get(self, task_id: str):
        if task_id != "memory_node:task":
            return None
        return MemoryNode(
            id=task_id,
            tags=(),
            timestamps=_timestamps(),
            content=Task(
                name="Reply",
                description="Reply to user.",
                input="User request.",
                output="agent_reply",
                prompt="Reply.",
                provider_id="memory_node:provider",
            ),
        )


class _FakeProviders:
    async def get(self, provider_id: str):
        if provider_id != "memory_node:provider":
            return None
        return MemoryNode(
            id=provider_id,
            tags=(),
            timestamps=_timestamps(),
            content=Provider(
                name="GLM 5.1",
                description="Test provider.",
                baml_surface="opencode_go.OpenCodeGoModelGlm51",
                model_id="glm-5.1",
                reasoning_effort="none",
            ),
        )


def _timestamps() -> MemoryTimestamps:
    now = datetime.now(timezone.utc)
    return MemoryTimestamps(created_at=now, updated_at=now, read_at=None)


if __name__ == "__main__":
    unittest.main()
