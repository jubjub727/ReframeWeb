from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


MAX_ACTION_DETAIL_CHARS = 1200


def payload_text(payload: Any, *keys: str) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, Mapping):
        return first_text(payload, keys)
    return ""


def memory_payload(payload: Any, default_title: str) -> tuple[str, str]:
    if isinstance(payload, Mapping):
        title = first_text(payload, ("title", "name", "summary")) or default_title
        description = (
            first_text(payload, ("description", "text", "memory", "value"))
            or title
        )
        return title, description
    text = str(payload).strip() if payload is not None else ""
    if not text:
        return default_title, default_title
    return text[:80].strip(), text


def first_text(payload: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and (text := str(value).strip()):
            return text
    return ""


def action_not_supported_detail(
    name: str,
    payload: Any,
    *,
    reason: str | None = None,
) -> str:
    pieces = [f"Action not supported: {name or '<empty>'}"]
    if reason:
        pieces.append(f"reason={reason}")
    pieces.append(f"payload={payload_preview(payload)}")
    return " ".join(pieces)


def malformed_detail(name: str, payload: Any) -> str:
    return f"Malformed action payload: {name} payload={payload_preview(payload)}"


def payload_preview(payload: Any) -> str:
    try:
        text = json.dumps(payload, sort_keys=True, default=str)
    except TypeError:
        text = repr(payload)
    if len(text) <= MAX_ACTION_DETAIL_CHARS:
        return text
    return text[: MAX_ACTION_DETAIL_CHARS - 3].rstrip() + "..."
