from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from reframe_memory import open_memory_database
from reframe_memory.ids import memory_node_record_id

from reframe_memory.schema import MEMORY_RELATIONS
from reframe_agent_host.memory_browser.json_tools import json_ready
from reframe_agent_host.memory_readiness import require_memory_ready


class BrowserDatabase:
    async def __aenter__(self):
        self.database = await open_memory_database()
        await require_memory_ready(self.database)
        return self.database

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.database.close()


async def root_records(database) -> dict[str, dict[str, object]]:
    result = await database.query("SELECT * FROM memory_root ORDER BY name;")
    return {str(record["id"]): dict(json_ready(record)) for record in result_records(result)}


async def contains_relations(database) -> list[dict[str, object]]:
    result = await database.query("SELECT * FROM contains;")
    return [dict(json_ready(record)) for record in result_records(result)]


async def relations_for(database, record_id: str) -> dict[str, list[dict[str, object]]]:
    relations: dict[str, list[dict[str, object]]] = {}
    for table in MEMORY_RELATIONS:
        result = await database.query(
            f"SELECT * FROM {table} WHERE in = {record_id} OR out = {record_id};"
        )
        relations[table] = [dict(json_ready(record)) for record in result_records(result)]
    return relations


async def message_nodes(database, record_id: str) -> list[dict[str, object]]:
    relation_result = await database.query(
        f"""
        SELECT out, position FROM has_message
        WHERE in = {record_id}
        ORDER BY position ASC;
        """
    )
    messages: list[dict[str, object]] = []
    for relation in result_records(relation_result):
        message_id = memory_node_record_id(str(relation["out"]))
        message_result = await database.query(f"SELECT * FROM {message_id};")
        for record in result_records(message_result):
            ready = dict(json_ready(record))
            ready["position"] = relation.get("position")
            messages.append(ready)
    return messages


async def child_nodes(database, record_id: str, relation: str, order: str) -> list[dict[str, object]]:
    if relation not in ("has_conversation", "has_session_memory"):
        return []
    result = await database.query(
        f"SELECT * FROM {record_id}->{relation}->memory_node ORDER BY {order};"
    )
    return [dict(json_ready(record)) for record in result_records(result)]


def result_records(result: Any) -> list[Mapping[str, Any]]:
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, Mapping)]


def single_count(result: Any) -> int:
    records = result_records(result)
    if not records:
        return 0
    value = next(iter(records[0].values()), 0)
    return int(value or 0)
