from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from reframe_memory.ids import memory_node_record_id

from reframe_agent_host.memory_browser.catalog import TABLES, view_for
from reframe_agent_host.memory_browser.json_tools import json_ready
from reframe_agent_host.memory_browser.queries import (
    BrowserDatabase,
    child_nodes,
    contains_relations,
    message_nodes,
    relations_for,
    result_records,
    root_records,
    single_count,
)
from reframe_agent_host.memory_browser.summaries import (
    matches_view,
    node_summary,
    root_counts,
    roots_by_node,
)


async def overview() -> dict[str, object]:
    async with BrowserDatabase() as database:
        roots = await root_records(database)
        relations = await contains_relations(database)
        counts = root_counts(relations)
        total = single_count(
            await database.query("SELECT count() AS total FROM memory_node GROUP ALL;")
        )
    return {
        "total_nodes": total,
        "roots": [
            {
                "id": root_id,
                "name": root.get("name") or root_id,
                "description": root.get("description") or "",
                "count": counts.get(root_id, 0),
            }
            for root_id, root in roots.items()
        ],
    }


async def list_nodes(view_key: str, search: str, limit: int) -> dict[str, object]:
    view = view_for(view_key)
    async with BrowserDatabase() as database:
        roots = await root_records(database)
        relations = await contains_relations(database)
        result = await database.query(
            """
            SELECT * FROM memory_node
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1000;
            """,
        )
    grouped_roots = roots_by_node(relations)
    rows = [node_summary(record, grouped_roots, roots) for record in result_records(result)]
    rows = [row for row in rows if matches_view(row, view)]
    if search.strip():
        needle = search.strip().lower()
        rows = [row for row in rows if needle in row["search_text"]]
    return {
        "view": view.key,
        "items": [_public_row(row) for row in rows[: _clamped_limit(limit)]],
    }


async def node_detail(node_id: str) -> dict[str, object]:
    record_id = memory_node_record_id(node_id)
    async with BrowserDatabase() as database:
        roots = await root_records(database)
        relations = await contains_relations(database)
        record_result = await database.query(f"SELECT * FROM {record_id};")
        relation_rows = await relations_for(database, record_id)
        messages = await message_nodes(database, record_id)
        conversations = await child_nodes(
            database,
            record_id,
            "has_conversation",
            "updated_at DESC, created_at DESC",
        )
        session_memories = await child_nodes(
            database,
            record_id,
            "has_session_memory",
            "updated_at DESC, created_at DESC",
        )
    records = result_records(record_result)
    if not records:
        raise LookupError(f"memory node not found: {node_id}")
    return {
        "record": json_ready(records[0]),
        "summary": node_summary(records[0], roots_by_node(relations), roots),
        "relations": relation_rows,
        "messages": messages,
        "conversations": conversations,
        "session_memories": session_memories,
    }


async def update_node(node_id: str, tags: Any, content: Any) -> dict[str, object]:
    record_id = memory_node_record_id(node_id)
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ValueError("tags must be a list of strings")
    if not isinstance(content, Mapping):
        raise ValueError("content must be a JSON object")

    clean_tags = list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
    async with BrowserDatabase() as database:
        result = await database.query(
            f"""
            UPDATE {record_id} SET
                tags = $tags,
                content = $content,
                updated_at = time::now()
            RETURN AFTER;
            """,
            {"tags": clean_tags, "content": dict(content)},
        )
    records = result_records(result)
    if not records:
        raise LookupError(f"memory node not found: {node_id}")
    return {"record": json_ready(records[0])}


async def delete_node(node_id: str) -> dict[str, object]:
    record_id = memory_node_record_id(node_id)
    async with BrowserDatabase() as database:
        existing = result_records(await database.query(f"SELECT id FROM {record_id};"))
        if not existing:
            raise LookupError(f"memory node not found: {node_id}")
        for table in (
            "contains",
            "provides_task",
            "has_conversation",
            "has_message",
            "has_session_memory",
        ):
            await database.query(
                f"DELETE {table} WHERE in = {record_id} OR out = {record_id};"
            )
        deleted = result_records(await database.query(f"DELETE {record_id} RETURN BEFORE;"))
    if not deleted:
        raise LookupError(f"memory node not deleted: {node_id}")
    return {"deleted_id": node_id}


async def table_rows(table: str, limit: int) -> dict[str, object]:
    if table not in TABLES:
        raise ValueError(f"unknown table: {table}")
    order = "ORDER BY updated_at DESC, created_at DESC" if table == "memory_node" else ""
    async with BrowserDatabase() as database:
        result = await database.query(
            f"SELECT * FROM {table} {order} LIMIT {_clamped_limit(limit)};"
        )
    return {"table": table, "rows": json_ready(result_records(result))}


def _public_row(row: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in row.items() if key != "search_text"}


def _clamped_limit(limit: int) -> int:
    return max(1, min(limit, 500))
