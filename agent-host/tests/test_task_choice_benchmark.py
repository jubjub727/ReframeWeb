import unittest

from reframe_agent_host.benchmarks.config import (
    TASK_CHOICE_DEFAULT_MODEL_ID,
    TASK_CHOICE_DEFAULT_REASONING_EFFORT,
    TaskChoiceBenchmarkConfig,
)
from reframe_agent_host.benchmarks.runner import _task_choice_providers
from benchmark_fixtures import provider as _provider


class TaskChoiceBenchmarkTests(unittest.TestCase):
    def test_task_choice_defaults_to_glm_51_none(self):
        config = TaskChoiceBenchmarkConfig(
            session_id=None,
            runs=1,
            warmup_runs=0,
            delay_seconds=0,
            provider_cooldown_seconds=0,
        )

        self.assertEqual(TASK_CHOICE_DEFAULT_MODEL_ID, "glm-5.1")
        self.assertEqual(TASK_CHOICE_DEFAULT_REASONING_EFFORT, "none")
        self.assertEqual(config.task_choice_model_id, "glm-5.1")
        self.assertEqual(config.reasoning_efforts, ("none",))

    def test_task_choice_default_provider_filter(self):
        providers = (
            _provider("provider:deepseek", "opencode_go.OpenCodeGoModelDeepseekV4Flash"),
            _provider("provider:glm51", "opencode_go.OpenCodeGoModelGlm51"),
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
        self.assertEqual(selected[0].content.baml_surface, "opencode_go.OpenCodeGoModelGlm51")


if __name__ == "__main__":
    unittest.main()
