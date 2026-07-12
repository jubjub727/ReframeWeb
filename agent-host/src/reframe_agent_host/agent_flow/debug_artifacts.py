from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
import enum
import json
from pathlib import Path
from typing import Any
from collections.abc import Mapping


def dump_directory(name: str) -> Path:
    return Path(__file__).resolve().parents[3] / "debug-dumps" / name


def timestamp_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return jsonable(value.model_dump(mode="json"))
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [jsonable(item) for item in value]
    return str(value)


def request_summary(body: str) -> dict[str, Any]:
    summary: dict[str, Any] = {"body_chars": len(body)}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        summary["body_json"] = "invalid"
        return summary

    summary.update(
        body_json="valid",
        model=parsed.get("model"),
        reasoning_effort=parsed.get("reasoning_effort"),
        message_count=0,
        messages=[],
    )
    messages = parsed.get("messages")
    if isinstance(messages, list):
        summary["messages"] = [
            {
                "role": message.get("role"),
                "content_chars": content_chars(message.get("content")),
            }
            for message in messages
            if isinstance(message, dict)
        ]
        summary["message_count"] = len(summary["messages"])
    for key in ("max_tokens", "temperature"):
        if key in parsed:
            summary[key] = parsed[key]
    return summary


def request_body_payload(body: str) -> dict[str, Any]:
    summary = request_summary(body)
    payload = {
        "body_chars": summary["body_chars"],
        "body": body,
        "body_json": summary["body_json"],
    }
    if summary["body_json"] == "valid":
        payload["body"] = json.loads(body)
        payload["summary"] = {
            key: value
            for key, value in summary.items()
            if key not in {"body_chars", "body_json"}
        }
    return payload


def formatted_request_body(body: str) -> str:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return body
    return json.dumps(parsed, indent=2, sort_keys=True) + "\n"


def content_chars(value: Any) -> int | None:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, list):
        sizes = [size for item in value if (size := content_chars(item)) is not None]
        return sum(sizes) if sizes else None
    if isinstance(value, dict):
        sizes = [
            size
            for key in ("text", "content")
            if (size := content_chars(value.get(key))) is not None
        ]
        return sum(sizes) if sizes else None
    return None


def line_count(text: str) -> int:
    return 0 if text == "" else text.count("\n") + 1


def try_write_text(path: Path, text: str) -> bool:
    try:
        path.write_text(text, encoding="utf-8")
    except Exception:
        return False
    return True


def try_unlink(path: Path) -> None:
    try:
        path.unlink()
    except Exception:
        return
