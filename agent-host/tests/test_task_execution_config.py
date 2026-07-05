from pathlib import Path
import re


def test_task_execution_model_omits_reasoning_effort() -> None:
    clients_baml = (
        Path(__file__).resolve().parents[1] / "baml_src" / "clients.baml"
    ).read_text(encoding="utf-8")
    body = _client_body(clients_baml, "TaskExecutionModel")

    assert 'model "kimi-k2.6"' in body
    assert "reasoning_effort" not in body


def _client_body(source: str, name: str) -> str:
    match = re.search(
        rf"client<llm>\s+{re.escape(name)}\s+\{{(?P<body>.*?)\n\}}",
        source,
        flags=re.S,
    )
    assert match is not None
    return match.group("body")
