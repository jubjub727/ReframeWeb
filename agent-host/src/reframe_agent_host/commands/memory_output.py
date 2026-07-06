from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
from typing import Any


MEMORY_TYPE_ORDER = (
    "task",
    "current_session_memory",
    "past_session",
    "past_session_memory",
    "past_conversation",
    "past_conversation_message",
)
CURRENT_AWARE_MEMORY_TYPE_ORDER = (
    "task",
    "current_session",
    "current_session_memory",
    "current_conversation",
    "current_conversation_message",
    "past_session",
    "past_session_memory",
    "past_conversation",
    "past_conversation_message",
)


def memory_search_summary(hints: Any) -> str:
    tags = getattr(hints, "tags", None)
    strings = getattr(hints, "strings", None)
    tags_any = _format_terms(getattr(tags, "any_of", ()))
    tags_all = _format_terms(getattr(tags, "all_of", ()))
    tags_none = _format_terms(getattr(tags, "none_of", ()))
    strings_contains = _format_terms(getattr(strings, "contains", ()))
    strings_equals = _format_terms(getattr(strings, "equals", ()))
    return (
        f"tags_any={tags_any} "
        f"tags_all={tags_all} "
        f"tags_none={tags_none} "
        f"strings_contains={strings_contains} "
        f"strings_equals={strings_equals}"
    )


def search_depth_summary(depths: Any) -> str:
    depth_map = getattr(depths, "depths", {}) or {}
    if not isinstance(depth_map, Mapping) or not depth_map:
        return "domains=[]"

    domains = []
    for domain, timestamps in depth_map.items():
        domains.append(
            f"{domain}("
            f"created_after={getattr(timestamps, 'created_after', 'n/a')}, "
            f"updated_after={getattr(timestamps, 'updated_after', 'n/a')}, "
            f"read_after={getattr(timestamps, 'read_after', 'n/a')})"
        )
    return "domains=[" + "; ".join(domains) + "]"


def memory_type_counts_summary(
    memories: Any,
    current_session_id: str | None = None,
) -> str:
    counts = memory_type_counts(memories, current_session_id)
    total = sum(counts.values())
    pieces = [f"total={total}"]
    pieces.extend(
        f"{kind}={counts[kind]}"
        for kind in _memory_type_order(current_session_id)
    )
    return " ".join(pieces)


def selected_memory_type_counts_summary(
    memories: Any,
    selected_ids: Any,
    current_session_id: str | None = None,
) -> str:
    counts = selected_memory_type_counts(memories, selected_ids, current_session_id)
    total = sum(counts.values())
    pieces = [f"total={total}"]
    order = (*_memory_type_order(current_session_id), "unknown")
    pieces.extend(f"{kind}={counts[kind]}" for kind in order)
    return " ".join(pieces)


def memory_type_counts(
    memories: Any,
    current_session_id: str | None = None,
) -> dict[str, int]:
    counts = {kind: 0 for kind in _memory_type_order(current_session_id)}
    for kind, _node_id in _memory_records(memories, current_session_id):
        counts[kind] += 1
    return counts


def selected_memory_type_counts(
    memories: Any,
    selected_ids: Any,
    current_session_id: str | None = None,
) -> dict[str, int]:
    order = (*_memory_type_order(current_session_id), "unknown")
    counts = {kind: 0 for kind in order}
    memory_kinds_by_id = {
        node_id: kind
        for kind, node_id in _memory_records(memories, current_session_id)
        if node_id is not None
    }
    for selected_id in _terms(selected_ids):
        counts[memory_kinds_by_id.get(selected_id, "unknown")] += 1
    return counts


def _memory_records(
    memories: Any,
    current_session_id: str | None = None,
) -> tuple[tuple[str, str | None], ...]:
    sessions = _items(
        getattr(getattr(memories, "past_conversation_context", None), "sessions", ())
    )
    conversation_pairs = tuple(
        (session, conversation)
        for session in sessions
        for conversation in _items(getattr(session, "conversations", ()))
    )

    records: list[tuple[str, str | None]] = []
    tasks = _items(getattr(getattr(memories, "task_catalog", None), "tasks", ()))
    records.extend(("task", _node_id(task)) for task in tasks)
    records.extend(
        ("current_session_memory", _node_id(memory))
        for memory in _items(getattr(memories, "current_session_memories", ()))
    )
    records.extend(
        (_session_kind(session, current_session_id), _session_id(session))
        for session in sessions
    )
    records.extend(
        (
            _session_memory_kind(session, current_session_id),
            _node_id(memory),
        )
        for session in sessions
        for memory in _items(getattr(session, "session_memories", ()))
    )
    records.extend(
        (
            _conversation_kind(session, current_session_id),
            _node_id(getattr(conversation, "conversation", None)),
        )
        for session, conversation in conversation_pairs
    )
    records.extend(
        (
            _conversation_message_kind(session, current_session_id),
            _node_id(message),
        )
        for session, conversation in conversation_pairs
        for message in _items(getattr(conversation, "messages", ()))
    )
    return tuple(records)


def _memory_type_order(current_session_id: str | None) -> tuple[str, ...]:
    if current_session_id is None:
        return MEMORY_TYPE_ORDER
    return CURRENT_AWARE_MEMORY_TYPE_ORDER


def _session_kind(session: Any, current_session_id: str | None) -> str:
    if _is_current_session(session, current_session_id):
        return "current_session"
    return "past_session"


def _session_memory_kind(session: Any, current_session_id: str | None) -> str:
    if _is_current_session(session, current_session_id):
        return "current_session_memory"
    return "past_session_memory"


def _conversation_kind(session: Any, current_session_id: str | None) -> str:
    if _is_current_session(session, current_session_id):
        return "current_conversation"
    return "past_conversation"


def _conversation_message_kind(
    session: Any,
    current_session_id: str | None,
) -> str:
    if _is_current_session(session, current_session_id):
        return "current_conversation_message"
    return "past_conversation_message"


def _is_current_session(session: Any, current_session_id: str | None) -> bool:
    return current_session_id is not None and _session_id(session) == current_session_id


def _session_id(session: Any) -> str | None:
    if session is None:
        return None
    return _node_id(getattr(session, "session", session))


def _format_terms(values: Any) -> str:
    return json.dumps(list(_terms(values)), ensure_ascii=False)


def _terms(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        term = values.strip()
        return (term,) if term else ()

    terms = []
    for value in _items(values):
        term = str(value).strip()
        if term:
            terms.append(term)
    return tuple(terms)


def _items(values: Any) -> tuple[Any, ...]:
    if values is None:
        return ()
    if isinstance(values, tuple):
        return values
    if isinstance(values, Iterable) and not isinstance(values, (str, bytes)):
        return tuple(values)
    return (values,)


def _node_id(node: Any) -> str | None:
    node_id = getattr(node, "id", None)
    if node_id is None:
        return None
    text = str(node_id).strip()
    return text or None
