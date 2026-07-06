from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from reframe_agent_host.memory_browser.catalog import root_label
from reframe_agent_host.memory_browser.json_tools import json_ready, text_blob


def node_summary(
    record: Mapping[str, Any],
    roots_by_node: dict[str, tuple[str, ...]],
    roots: dict[str, dict[str, object]],
) -> dict[str, object]:
    node_id = str(record["id"])
    content = record.get("content") if isinstance(record.get("content"), Mapping) else {}
    root_ids = roots_by_node.get(node_id, ())
    root_names = [root_label(root_id, roots) for root_id in root_ids]
    title = _title(content, node_id)
    subtitle = _subtitle(content, root_names)
    ready = json_ready(record)
    search_text = " ".join(
        [node_id, title, subtitle, " ".join(root_names), text_blob(ready)]
    ).lower()
    return {
        "id": node_id,
        "title": title,
        "subtitle": subtitle,
        "kind": _kind(content, root_names),
        "tags": ready.get("tags") or [],
        "root_ids": list(root_ids),
        "roots": root_names,
        "created_at": ready.get("created_at"),
        "updated_at": ready.get("updated_at"),
        "read_at": ready.get("read_at"),
        "search_text": search_text,
        "content": ready.get("content") or {},
    }


def matches_view(row: Mapping[str, Any], view) -> bool:
    if view.key == "raw":
        return True
    if view.key == "messages":
        content = row.get("content")
        return isinstance(content, Mapping) and {"role", "content"} <= set(content)
    return bool(set(row.get("root_ids") or ()) & set(view.root_ids))


def roots_by_node(relations: list[Mapping[str, Any]]) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for relation in relations:
        out_id = str(relation.get("out"))
        in_id = str(relation.get("in"))
        grouped.setdefault(out_id, []).append(in_id)
    return {node_id: tuple(root_ids) for node_id, root_ids in grouped.items()}


def root_counts(relations: list[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for relation in relations:
        root_id = str(relation.get("in"))
        counts[root_id] = counts.get(root_id, 0) + 1
    return counts


def _title(content: Mapping[str, Any], fallback: str) -> str:
    for key in ("name", "title"):
        value = content.get(key)
        if value:
            return str(value)
    if content.get("role") and content.get("content"):
        return f"{content['role']}: {str(content['content'])[:80]}"
    return fallback


def _subtitle(content: Mapping[str, Any], root_names: list[str]) -> str:
    for key in ("description", "input", "baml_surface", "model_id"):
        value = content.get(key)
        if value:
            return str(value)
    return ", ".join(root_names)


def _kind(content: Mapping[str, Any], root_names: list[str]) -> str:
    if content.get("role") and content.get("content"):
        return "Conversation Message"
    return root_names[0] if root_names else "Memory Node"
