import unittest
from unittest.mock import patch

from reframe_agent_host.memory_browser.catalog import TABLES
from reframe_agent_host.memory_browser.records import (
    delete_node,
    list_nodes,
    table_rows,
)
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


class MemoryBrowserListingTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_view_is_not_truncated_by_unrelated_newer_nodes(self) -> None:
        database = _LargeBrowserDatabase()

        with patch(
            "reframe_agent_host.memory_browser.records.BrowserDatabase",
            return_value=database,
        ):
            result = await list_nodes("providers", "")

        self.assertEqual(len(result["items"]), 73)
        self.assertTrue(all("Providers" in item["roots"] for item in result["items"]))
        node_query = next(query for query in database.queries if "FROM memory_node" in query)
        self.assertNotIn("LIMIT", node_query)

    async def test_raw_tables_return_every_row(self) -> None:
        database = _LargeBrowserDatabase()

        with patch(
            "reframe_agent_host.memory_browser.records.BrowserDatabase",
            return_value=database,
        ):
            result = await table_rows("memory_node")

        self.assertEqual(len(result["rows"]), 1_273)
        self.assertNotIn("LIMIT", database.queries[-1])


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


class _LargeBrowserDatabase:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.unrelated_nodes = [
            {
                "id": f"memory_node:unrelated_{index}",
                "tags": [],
                "content": {"name": f"Unrelated {index}"},
            }
            for index in range(1_200)
        ]
        self.provider_nodes = [
            {
                "id": f"memory_node:provider_{index}",
                "tags": ["provider"],
                "content": {
                    "name": f"Provider {index}",
                    "model_id": f"model-{index}",
                },
            }
            for index in range(73)
        ]

    async def __aenter__(self):
        return self

    async def __aexit__(self, _error_type, _error, _traceback) -> None:
        return None

    async def query(self, query: str):
        self.queries.append(query)
        if "FROM memory_root" in query:
            return [
                {
                    "id": "memory_root:providers",
                    "name": "Providers",
                    "description": "Provider records",
                }
            ]
        if "FROM contains" in query:
            return [
                {
                    "in": "memory_root:providers",
                    "out": node["id"],
                }
                for node in self.provider_nodes
            ]
        if "FROM memory_node" in query:
            return self.unrelated_nodes + self.provider_nodes
        return []


if __name__ == "__main__":
    unittest.main()
