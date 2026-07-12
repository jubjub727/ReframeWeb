import unittest
from unittest.mock import patch

from reframe_agent_host.memory_browser.catalog import TABLES
from reframe_agent_host.memory_browser.records import delete_node
from reframe_memory.schema import MEMORY_RELATIONS, SCHEMA_STATEMENTS


class MemoryBrowserRelationTests(unittest.TestCase):
    def test_all_memory_relations_are_browsable(self) -> None:
        for relation in MEMORY_RELATIONS:
            self.assertIn(relation, TABLES)

    def test_all_memory_relations_are_defined_by_the_schema(self) -> None:
        schema = "\n".join(SCHEMA_STATEMENTS)
        for relation in MEMORY_RELATIONS:
            self.assertIn(f"DEFINE TABLE IF NOT EXISTS {relation} ", schema)


class MemoryBrowserDeletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_deletion_removes_every_relation_before_the_node(self) -> None:
        database = _RecordingDatabase()

        with patch(
            "reframe_agent_host.memory_browser.records.BrowserDatabase",
            return_value=database,
        ):
            result = await delete_node("memory_node:task")

        self.assertEqual(result, {"deleted_id": "memory_node:task"})
        relation_deletes = [
            query
            for query in database.queries
            if query.startswith("DELETE ") and " WHERE in = " in query
        ]
        self.assertEqual(
            relation_deletes,
            [
                (
                    f"DELETE {relation} WHERE in = memory_node:task "
                    "OR out = memory_node:task;"
                )
                for relation in MEMORY_RELATIONS
            ],
        )


class _RecordingDatabase:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, _error_type, _error, _traceback) -> None:
        return None

    async def query(self, query: str):
        self.queries.append(query)
        if query.startswith("SELECT id FROM "):
            return [{"id": "memory_node:task"}]
        if query.startswith("DELETE memory_node:task RETURN BEFORE"):
            return [{"id": "memory_node:task"}]
        return []


if __name__ == "__main__":
    unittest.main()
