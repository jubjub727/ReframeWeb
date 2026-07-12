import unittest
from datetime import datetime, timezone

from reframe_agent_host.benchmarks.task_choice_config import (
    TASK_CHOICE_DEFAULT_MODEL_ID,
    TASK_CHOICE_DEFAULT_REASONING_EFFORT,
    TaskChoiceBenchmarkConfig,
)
from reframe_agent_host.benchmarks.task_choice_runner import _task_choice_providers
from reframe_memory import MemoryNode, MemoryTimestamps, Provider


class TaskChoiceBenchmarkTests(unittest.TestCase):
    def test_task_choice_defaults_to_kimi_k25_high(self):
        config = TaskChoiceBenchmarkConfig(
            session_id=None,
            runs=1,
            warmup_runs=0,
            delay_seconds=0,
            provider_cooldown_seconds=0,
        )

        self.assertEqual(TASK_CHOICE_DEFAULT_MODEL_ID, "kimi-k2.5")
        self.assertEqual(TASK_CHOICE_DEFAULT_REASONING_EFFORT, "high")
        self.assertEqual(config.task_choice_model_id, "kimi-k2.5")
        self.assertEqual(config.reasoning_efforts, ("high",))

    def test_task_choice_default_provider_filter(self):
        providers = (
            _provider("provider:deepseek", "opencode_go.OpenCodeGoModelDeepseekV4Flash"),
            _provider("provider:kimi25", "opencode_go.OpenCodeGoModelKimiK25"),
        )
        config = TaskChoiceBenchmarkConfig(
            session_id=None,
            runs=1,
            warmup_runs=0,
            delay_seconds=0,
            provider_cooldown_seconds=0,
        )

        selected = _task_choice_providers(providers, config)

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].content.baml_surface, "opencode_go.OpenCodeGoModelKimiK25")


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
