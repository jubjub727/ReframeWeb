from __future__ import annotations


MEMORY_RELATIONS: tuple[str, ...] = (
    "contains",
    "provides_task",
    "has_conversation",
    "has_message",
    "has_session_memory",
    "history",
    "actions",
    "action",
)


SCHEMA_STATEMENTS: tuple[str, ...] = (
    "DEFINE TABLE IF NOT EXISTS memory_root SCHEMAFULL;",
    "DEFINE FIELD IF NOT EXISTS name ON TABLE memory_root TYPE string;",
    "DEFINE FIELD IF NOT EXISTS description ON TABLE memory_root TYPE string;",
    "DEFINE TABLE IF NOT EXISTS memory_node SCHEMAFULL;",
    "DEFINE FIELD IF NOT EXISTS tags ON TABLE memory_node TYPE array<string> DEFAULT [];",
    "DEFINE FIELD OVERWRITE content ON TABLE memory_node FLEXIBLE TYPE object;",
    "DEFINE FIELD IF NOT EXISTS created_at ON TABLE memory_node TYPE datetime;",
    "DEFINE FIELD IF NOT EXISTS updated_at ON TABLE memory_node TYPE datetime;",
    "DEFINE FIELD IF NOT EXISTS read_at ON TABLE memory_node TYPE option<datetime>;",
    "DEFINE TABLE IF NOT EXISTS contains TYPE RELATION IN memory_root OUT memory_node;",
    "DEFINE TABLE IF NOT EXISTS provides_task TYPE RELATION IN memory_node OUT memory_node;",
    "DEFINE TABLE IF NOT EXISTS has_conversation TYPE RELATION IN memory_node OUT memory_node;",
    "DEFINE TABLE IF NOT EXISTS has_message TYPE RELATION IN memory_node OUT memory_node;",
    "DEFINE FIELD IF NOT EXISTS position ON TABLE has_message TYPE int;",
    "DEFINE TABLE IF NOT EXISTS has_session_memory TYPE RELATION IN memory_node OUT memory_node;",
    "DEFINE TABLE IF NOT EXISTS history TYPE RELATION IN memory_node OUT memory_node;",
    "DEFINE FIELD IF NOT EXISTS position ON TABLE history TYPE int;",
    "DEFINE TABLE IF NOT EXISTS actions TYPE RELATION IN memory_node OUT memory_node;",
    "DEFINE FIELD IF NOT EXISTS position ON TABLE actions TYPE int;",
    "DEFINE TABLE IF NOT EXISTS action TYPE RELATION IN memory_node OUT memory_node;",
)
