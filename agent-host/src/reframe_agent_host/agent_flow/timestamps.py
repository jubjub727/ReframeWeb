from __future__ import annotations

from typing import Any


def timestamp_fields(node: Any) -> dict[str, str]:
    timestamps = node.timestamps
    return {
        "created_at": timestamps.created_at.isoformat(),
        "updated_at": timestamps.updated_at.isoformat(),
        "read_at": timestamps.read_at.isoformat() if timestamps.read_at else "NONE",
    }
