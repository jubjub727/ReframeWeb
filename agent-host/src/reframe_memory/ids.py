from __future__ import annotations

import re


_MEMORY_NODE_ID_PATTERN = re.compile(r"memory_node:[A-Za-z0-9_-]+")


def memory_node_record_id(record_id: str) -> str:
    if not _MEMORY_NODE_ID_PATTERN.fullmatch(record_id):
        msg = f"expected memory_node record id, got {record_id!r}"
        raise ValueError(msg)

    return record_id
