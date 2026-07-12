from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from baml_sdk import task_execution as baml_task_execution
from reframe_agent_host.agent_flow.debug_artifacts import (
    dump_directory,
    formatted_request_body,
    line_count,
    request_summary,
    timestamp_id,
    try_write_text,
)
from reframe_memory import ProviderNode, TaskNode


@dataclass
class TaskExecutionDebugDump:
    prompt_path: Path
    metadata_path: Path
    request_path: Path
    latest_prompt_path: Path
    latest_metadata_path: Path
    latest_request_path: Path
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def begin(
        cls,
        *,
        selected_task: TaskNode,
        provider: ProviderNode,
        client_name: str,
        full_task_prompt: str,
    ) -> TaskExecutionDebugDump | None:
        try:
            return cls._begin(
                selected_task=selected_task,
                provider=provider,
                client_name=client_name,
                full_task_prompt=full_task_prompt,
            )
        except Exception:
            return None

    @classmethod
    def _begin(
        cls,
        *,
        selected_task: TaskNode,
        provider: ProviderNode,
        client_name: str,
        full_task_prompt: str,
    ) -> TaskExecutionDebugDump | None:
        if os.environ.get("REFRAME_TASK_EXECUTION_DUMP", "1").lower() in {
            "0",
            "false",
            "off",
            "no",
        }:
            return None

        dump_dir = _dump_dir()
        dump_dir.mkdir(parents=True, exist_ok=True)
        timestamp = _timestamp()
        prompt_path = dump_dir / f"{timestamp}.prompt.txt"
        metadata_path = dump_dir / f"{timestamp}.metadata.json"
        request_path = dump_dir / f"{timestamp}.request.json"
        latest_prompt_path = dump_dir / "latest.prompt.txt"
        latest_metadata_path = dump_dir / "latest.metadata.json"
        latest_request_path = dump_dir / "latest.request.json"
        if not try_write_text(prompt_path, full_task_prompt):
            return None
        try_write_text(latest_prompt_path, full_task_prompt)

        dump = cls(
            prompt_path=prompt_path,
            metadata_path=metadata_path,
            request_path=request_path,
            latest_prompt_path=latest_prompt_path,
            latest_metadata_path=latest_metadata_path,
            latest_request_path=latest_request_path,
            metadata={
                "status": "started",
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "prompt_path": str(prompt_path),
                "latest_prompt_path": str(latest_prompt_path),
                "request_path": str(request_path),
                "latest_request_path": str(latest_request_path),
                "selected_task": {
                    "id": selected_task.id,
                    "name": selected_task.content.name,
                    "provider_id": selected_task.content.provider_id,
                },
                "provider": {
                    "id": provider.id,
                    "name": provider.content.name,
                    "baml_surface": provider.content.baml_surface,
                    "model_id": provider.content.model_id,
                    "reasoning_effort": provider.content.reasoning_effort,
                },
                "client_name": client_name,
                "prompt": {
                    "chars": len(full_task_prompt),
                    "lines": line_count(full_task_prompt),
                },
            },
        )
        dump.write()
        return dump

    def record_request(self, request: Any) -> None:
        try:
            self._record_request(request)
        except Exception:
            return

    def _record_request(self, request: Any) -> None:
        body = str(getattr(request, "body", ""))
        self._write_request_body(body)
        self.metadata["request"] = request_summary(body)
        self.write()

    def _write_request_body(self, body: str) -> None:
        text = formatted_request_body(body)
        try_write_text(self.request_path, text)
        try_write_text(self.latest_request_path, text)

    def record_result(
        self,
        *,
        elapsed_seconds: float,
        result: baml_task_execution.TaskExecutionResult,
    ) -> None:
        try:
            returns = result.returns
            self.metadata.update(
                {
                    "status": "ok",
                    "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                    "elapsed_seconds": elapsed_seconds,
                    "result": {
                        "return_count": len(returns),
                        "return_names": [item.name for item in returns],
                        "json": result.model_dump(mode="json"),
                    },
                }
            )
            self.write()
        except Exception:
            return

    def record_error(self, *, elapsed_seconds: float, error: Exception) -> None:
        try:
            self.metadata.update(
                {
                    "status": "error",
                    "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                    "elapsed_seconds": elapsed_seconds,
                    "error": {
                        "type": type(error).__name__,
                        "message": str(error),
                    },
                }
            )
            self.write()
        except Exception:
            return

    def write(self) -> None:
        text = json.dumps(self.metadata, indent=2, sort_keys=True) + "\n"
        try_write_text(self.metadata_path, text)
        try_write_text(self.latest_metadata_path, text)


def _dump_dir() -> Path:
    return dump_directory("task-execution")


def _timestamp() -> str:
    return timestamp_id()
