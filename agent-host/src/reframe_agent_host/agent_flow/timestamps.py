from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def current_timestamp() -> str:
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return stamp.replace("+00:00", "Z")


def timestamp_fields(node: Any) -> dict[str, str]:
    timestamps = node.timestamps
    return {
        "created_at": timestamps.created_at.isoformat(),
        "updated_at": timestamps.updated_at.isoformat(),
        "read_at": timestamps.read_at.isoformat() if timestamps.read_at else "NONE",
    }
