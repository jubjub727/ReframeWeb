from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from collections.abc import Mapping
from datetime import date, datetime, timezone
import enum
import json
import os
from pathlib import Path
from typing import Any


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
                _try_unlink(path)
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
            "inputs": _jsonable(inputs),
        }
        if request is not None:
            payload["request"] = _request_payload(request)
        if result is not None:
            payload["result"] = _jsonable(result)
        if error is not None:
            payload["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }

        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if not _try_write_text(run_path, text):
            return
        _try_write_text(latest_path, text)
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
        _try_write_text(self.run_dir / "index.json", text)
        _try_write_text(self.latest_dir / "index.json", text)

    def _started_at(self) -> str:
        parsed = datetime.strptime(self.run_id, "%Y%m%dT%H%M%S%fZ")
        return parsed.replace(tzinfo=timezone.utc).isoformat()


def _dump_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "debug-dumps" / "prompt-layers"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(item) for item in value]
    return str(value)


def _request_payload(request: Any) -> dict[str, Any]:
    body = str(getattr(request, "body", ""))
    payload: dict[str, Any] = {
        "body_chars": len(body),
        "body": body,
    }
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        payload["body_json"] = "invalid"
    else:
        payload["body_json"] = "valid"
        payload["body"] = parsed
        payload["summary"] = _request_body_summary(parsed)
    return payload


def _request_body_summary(body: dict[str, Any]) -> dict[str, Any]:
    messages = body.get("messages")
    message_summaries = []
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            message_summaries.append(
                {
                    "role": message.get("role"),
                    "content_chars": _content_chars(message.get("content")),
                },
            )

    summary = {
        "model": body.get("model"),
        "reasoning_effort": body.get("reasoning_effort"),
        "message_count": len(message_summaries),
        "messages": message_summaries,
    }
    if "max_tokens" in body:
        summary["max_tokens"] = body["max_tokens"]
    if "temperature" in body:
        summary["temperature"] = body["temperature"]
    return summary


def _content_chars(value: Any) -> int | None:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, list):
        total = 0
        found = False
        for item in value:
            size = _content_chars(item)
            if size is not None:
                total += size
                found = True
        return total if found else None
    if isinstance(value, dict):
        total = 0
        found = False
        for key in ("text", "content"):
            size = _content_chars(value.get(key))
            if size is not None:
                total += size
                found = True
        return total if found else None
    return None


def _try_write_text(path: Path, text: str) -> bool:
    try:
        path.write_text(text, encoding="utf-8")
    except Exception:
        return False
    return True


def _try_unlink(path: Path) -> None:
    try:
        path.unlink()
    except Exception:
        return
