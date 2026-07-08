from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from typing import TYPE_CHECKING, Any

from reframe_memory.ids import memory_node_record_id
from reframe_memory.models import (
    Action,
    ActionNode,
    SessionAction,
    SessionActionNode,
    TaskHistory,
    TaskHistoryMemoryNode,
    TaskHistoryNode,
    TaskHistoryNodeMemoryNode,
)
from reframe_memory.records import memory_node_from_record

if TYPE_CHECKING:
    from reframe_memory.database import MemoryDatabase


@dataclass(frozen=True)
class TaskHistoryRecord:
    node: TaskHistoryNodeMemoryNode
    actions: tuple[ActionNode, ...]


@dataclass
class TaskHistoryStore:
    database: MemoryDatabase

    async def create(self, tags: Sequence[str] = ()) -> TaskHistoryMemoryNode:
        record = await self._create_node(
            content={},
            tags=_tags("task-history", tags),
        )
        return task_history_from_record(record)

    async def record_action(
        self,
        *,
        name: str,
        input: object,
        output: object,
        tags: Sequence[str] = (),
    ) -> SessionActionNode:
        action = await self.create_action(
            name=name,
            input=input,
            output=output,
            tags=tags,
        )
        return await self.create_session_action(action.id, tags=tags)

    async def create_action(
        self,
        *,
        name: str,
        input: object,
        output: object,
        tags: Sequence[str] = (),
    ) -> ActionNode:
        record = await self._create_node(
            content={
                "name": name,
                "input": _json_value(input),
                "output": _json_value(output),
            },
            tags=_tags("action", tags),
        )
        return action_from_record(record)

    async def create_session_action(
        self,
        action_id: str,
        tags: Sequence[str] = (),
    ) -> SessionActionNode:
        action_record_id = memory_node_record_id(action_id)
        record = await self._create_node(
            content={},
            tags=_tags("session-action", tags),
        )
        session_action_record_id = memory_node_record_id(str(record["id"]))
        await self.database.query(
            f"RELATE {session_action_record_id}->action->{action_record_id};",
        )
        return session_action_from_record(record)

    async def append_node(
        self,
        task_history_id: str,
        *,
        session_id: str,
        conversation_id: str,
        actions: Sequence[str],
        tags: Sequence[str] = (),
    ) -> TaskHistoryNodeMemoryNode:
        task_history_record_id = memory_node_record_id(task_history_id)
        record = await self._create_node(
            content={
                "session": memory_node_record_id(session_id),
                "conversation": memory_node_record_id(conversation_id),
            },
            tags=_tags("task-history-node", tags),
        )
        node_record_id = memory_node_record_id(str(record["id"]))
        for position, action_id in enumerate(actions):
            action_record_id = memory_node_record_id(action_id)
            await self.database.query(
                f"""
                RELATE {node_record_id}->actions->{action_record_id}
                SET position = $position;
                """,
                {"position": position},
            )

        history_position = await self._next_position(
            "history",
            task_history_record_id,
        )
        await self.database.query(
            f"""
            RELATE {task_history_record_id}->history->{node_record_id}
            SET position = $position;
            UPDATE {task_history_record_id} SET updated_at = time::now();
            """,
            {"position": history_position},
        )
        return task_history_node_from_record(record)

    async def records(self, task_history_id: str) -> tuple[TaskHistoryRecord, ...]:
        task_history_record_id = memory_node_record_id(task_history_id)
        relation_result = await self.database.query(
            f"""
            SELECT out, position FROM history
            WHERE in = {task_history_record_id}
            ORDER BY position ASC;
            """,
        )
        records: list[TaskHistoryRecord] = []
        for relation in _records(relation_result):
            node = await self._task_history_node(str(relation["out"]))
            if node is None:
                continue
            records.append(
                TaskHistoryRecord(
                    node=node,
                    actions=tuple(await self.actions_for_node(node.id)),
                ),
            )
        return tuple(records)

    async def actions_for_node(self, task_history_node_id: str) -> list[ActionNode]:
        node_record_id = memory_node_record_id(task_history_node_id)
        relation_result = await self.database.query(
            f"""
            SELECT out, position FROM actions
            WHERE in = {node_record_id}
            ORDER BY position ASC;
            """,
        )
        actions: list[ActionNode] = []
        for relation in _records(relation_result):
            action = await self._action_for_session_action(str(relation["out"]))
            if action is not None:
                actions.append(action)
        return actions

    async def render(self, task_history_id: str) -> str:
        records = await self.records(task_history_id)
        if not records:
            return "No recorded actions."

        rendered: list[str] = []
        for record in records:
            rendered.append(f"- Session: {record.node.content.session}")
            rendered.append(f"  Conversation: {record.node.content.conversation}")
            rendered.append("  Actions:")
            if not record.actions:
                rendered.append("  - Action: none")
                continue
            for action in record.actions:
                rendered.append("  - Action:")
                rendered.append(f"      name: {action.content.name}")
                rendered.append("      input:")
                rendered.append(_indent(_json_text(action.content.input), 8))
                rendered.append("      output:")
                rendered.append(_indent(_json_text(action.content.output), 8))
        return "\n".join(rendered)

    async def _create_node(
        self,
        *,
        content: Mapping[str, Any],
        tags: Sequence[str],
    ) -> Mapping[str, Any]:
        result = await self.database.query(
            """
            CREATE memory_node SET
                tags = $tags,
                content = $content,
                created_at = time::now(),
                updated_at = time::now(),
                read_at = NONE;
            """,
            {
                "tags": list(dict.fromkeys(tag.strip() for tag in tags if tag.strip())),
                "content": dict(content),
            },
        )
        return _first_record(result)

    async def _task_history_node(
        self,
        task_history_node_id: str,
    ) -> TaskHistoryNodeMemoryNode | None:
        record_id = memory_node_record_id(task_history_node_id)
        result = await self.database.query(f"SELECT * FROM {record_id};")
        records = _records(result)
        if not records:
            return None
        return task_history_node_from_record(records[0])

    async def _action_for_session_action(
        self,
        session_action_id: str,
    ) -> ActionNode | None:
        session_action_record_id = memory_node_record_id(session_action_id)
        relation_result = await self.database.query(
            f"""
            SELECT out FROM action
            WHERE in = {session_action_record_id}
            LIMIT 1;
            """,
        )
        relation_records = _records(relation_result)
        if not relation_records:
            return None

        action_record_id = memory_node_record_id(str(relation_records[0]["out"]))
        action_result = await self.database.query(f"SELECT * FROM {action_record_id};")
        action_records = _records(action_result)
        if not action_records:
            return None
        return action_from_record(action_records[0])

    async def _next_position(self, relation: str, parent_record_id: str) -> int:
        result = await self.database.query(
            f"""
            SELECT position FROM {relation}
            WHERE in = {parent_record_id}
            ORDER BY position DESC
            LIMIT 1;
            """,
        )
        records = _records(result)
        if not records:
            return 0
        return int(records[0]["position"]) + 1


def task_history_from_record(record: Mapping[str, Any]) -> TaskHistoryMemoryNode:
    return memory_node_from_record(record, _parse_task_history)


def task_history_node_from_record(
    record: Mapping[str, Any],
) -> TaskHistoryNodeMemoryNode:
    return memory_node_from_record(record, _parse_task_history_node)


def session_action_from_record(record: Mapping[str, Any]) -> SessionActionNode:
    return memory_node_from_record(record, _parse_session_action)


def action_from_record(record: Mapping[str, Any]) -> ActionNode:
    return memory_node_from_record(record, _parse_action)


def _parse_task_history(_content: Mapping[str, Any]) -> TaskHistory:
    return TaskHistory()


def _parse_task_history_node(content: Mapping[str, Any]) -> TaskHistoryNode:
    return TaskHistoryNode(
        session=memory_node_record_id(str(content["session"])),
        conversation=memory_node_record_id(str(content["conversation"])),
    )


def _parse_session_action(_content: Mapping[str, Any]) -> SessionAction:
    return SessionAction()


def _parse_action(content: Mapping[str, Any]) -> Action:
    return Action(
        name=str(content["name"]),
        input=content.get("input", {}),
        output=content.get("output", {}),
    )


def _tags(kind: str, tags: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys((kind, "task-history", *tags)))


def _json_value(value: object) -> object:
    return json.loads(json.dumps(value, default=str))


def _json_text(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=str)


def _indent(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(f"{prefix}{line}" for line in text.splitlines())


def _records(result: Any) -> list[Mapping[str, Any]]:
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, Mapping)]


def _first_record(result: Any) -> Mapping[str, Any]:
    records = _records(result)
    if not records:
        raise ValueError("query did not return a memory node")
    return records[0]
