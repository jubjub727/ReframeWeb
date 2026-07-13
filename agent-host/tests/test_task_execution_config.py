from pathlib import Path
import re
import unittest


class TaskModelAssignmentTests(unittest.TestCase):
    def test_task_execution_model_uses_glm51_no_reasoning(self) -> None:
        body = _client_body(_model_source("execution"), "TaskExecutionModel")

        self.assertIn('model: "glm-5.1"', body)
        self.assertIn('reasoning_effort: "none"', body)

    def test_task_completion_model_uses_glm51_no_reasoning(self) -> None:
        body = _client_body(_model_source("completion"), "TaskCompletionModel")

        self.assertIn('model: "glm-5.1"', body)
        self.assertIn('reasoning_effort: "none"', body)


def _model_source(area: str) -> str:
    path = (
        Path(__file__).resolve().parents[1]
        / "baml_src"
        / "ns_task"
        / area
        / "client.baml"
    )
    return path.read_text(encoding="utf-8")


def _client_body(source: str, name: str) -> str:
    match = re.search(
        rf"client<llm>\s+{re.escape(name)}\s+\{{(?P<body>.*?)\n\}}",
        source,
        flags=re.S,
    )
    assert match is not None
    return match.group("body")


if __name__ == "__main__":
    unittest.main()
