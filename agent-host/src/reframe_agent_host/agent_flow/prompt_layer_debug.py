from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from reframe_agent_host.agent_flow.debug_artifacts import (
    dump_directory,
    jsonable,
    request_body_payload,
    timestamp_id,
    try_unlink,
    try_write_text,
)


@dataclass
class PromptLayerDebugSession:
    run_id: str
    run_dir: Path
    latest_dir: Path
    current_user_request: str
    layers: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def begin(cls, *, current_user_request: str) -> PromptLayerDebugSession | None:
        try:
            return cls._begin(current_user_request=current_user_request)
        except Exception:
            return None

    @classmethod
    def _begin(cls, *, current_user_request: str) -> PromptLayerDebugSession | None:
        if os.environ.get("REFRAME_PROMPT_LAYER_DUMP", "1").lower() in {
            "0",
            "false",
            "off",
            "no",
        }:
            return None

        run_id = _timestamp()
        root = _dump_dir()
        run_dir = root / run_id
        latest_dir = root / "latest"
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            return None
        try:
            latest_dir.mkdir(parents=True, exist_ok=True)
            for path in latest_dir.glob("*.json"):
                try_unlink(path)
        except Exception:
            pass

        session = cls(
            run_id=run_id,
            run_dir=run_dir,
            latest_dir=latest_dir,
            current_user_request=current_user_request,
        )
        session._write_index()
        return session

    def write_layer(
        self,
        *,
        order: int,
        name: str,
        inputs: Mapping[str, Any],
        result: Any = None,
        request: Any = None,
        elapsed_seconds: float | None = None,
        error: Exception | None = None,
    ) -> None:
        try:
            self._write_layer(
                order=order,
                name=name,
                inputs=inputs,
                result=result,
                request=request,
                elapsed_seconds=elapsed_seconds,
                error=error,
            )
        except Exception:
            return

    def _write_layer(
        self,
        *,
        order: int,
        name: str,
        inputs: Mapping[str, Any],
        result: Any,
        request: Any,
        elapsed_seconds: float | None,
        error: Exception | None,
    ) -> None:
        filename = f"{order:02d}-{name}.json"
        run_path = self.run_dir / filename
        latest_path = self.latest_dir / filename
        status = "error" if error is not None else "ok"
        payload: dict[str, Any] = {
            "run_id": self.run_id,
            "layer": name,
            "order": order,
            "status": status,
            "current_user_request": self.current_user_request,
            "elapsed_seconds": elapsed_seconds,
            "inputs": jsonable(inputs),
        }
        if request is not None:
            payload["request"] = request_body_payload(
                str(getattr(request, "body", ""))
            )
        if result is not None:
            payload["result"] = jsonable(result)
        if error is not None:
            payload["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }

        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if not try_write_text(run_path, text):
            return
        try_write_text(latest_path, text)
        self._upsert_layer_index(
            {
                "order": order,
                "layer": name,
                "status": status,
                "elapsed_seconds": elapsed_seconds,
                "path": str(run_path),
                "latest_path": str(latest_path),
            },
        )
        self._write_index()

    def _upsert_layer_index(self, entry: dict[str, Any]) -> None:
        self.layers = [
            layer
            for layer in self.layers
            if not (
                layer.get("order") == entry["order"]
                and layer.get("layer") == entry["layer"]
            )
        ]
        self.layers.append(entry)
        self.layers.sort(key=lambda layer: (layer["order"], layer["layer"]))

    def _write_index(self) -> None:
        payload = {
            "run_id": self.run_id,
            "started_at_utc": self._started_at(),
            "current_user_request": self.current_user_request,
            "run_dir": str(self.run_dir),
            "latest_dir": str(self.latest_dir),
            "layers": self.layers,
        }
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        try_write_text(self.run_dir / "index.json", text)
        try_write_text(self.latest_dir / "index.json", text)

    def _started_at(self) -> str:
        parsed = datetime.strptime(self.run_id, "%Y%m%dT%H%M%S%fZ")
        return parsed.replace(tzinfo=timezone.utc).isoformat()


def _dump_dir() -> Path:
    return dump_directory("prompt-layers")


def _timestamp() -> str:
    return timestamp_id()
