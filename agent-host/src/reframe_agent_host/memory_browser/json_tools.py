from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any


def json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [json_ready(item) for item in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def text_blob(value: Any) -> str:
    ready = json_ready(value)
    if isinstance(ready, Mapping):
        parts = [str(key) for key in ready]
        parts.extend(text_blob(item) for item in ready.values())
        return " ".join(parts)
    if isinstance(ready, list):
        return " ".join(text_blob(item) for item in ready)
    return str(ready)
