from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def records(result: Any) -> list[Mapping[str, Any]]:
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, Mapping)]


def first_record(result: Any) -> Mapping[str, Any]:
    found = records(result)
    if not found:
        raise ValueError("query did not return a memory node")
    return found[0]
