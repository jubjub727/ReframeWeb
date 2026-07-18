from __future__ import annotations

from datetime import datetime, timezone
import unittest

from reframe_memory import FilesystemMemory
from reframe_memory.filesystem_memories import FilesystemMemoryStore


class FilesystemMemoryStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_and_resolve_filesystem_memory_node(self) -> None:
        database = _FakeDatabase()
        store = FilesystemMemoryStore(database)

        created = await store.create(
            FilesystemMemory(
                title="Design",
                description="Project decisions",
                source_kind="directory",
                source_path="D:\\memories\\design",
            ),
            tags=("workspace", "design"),
        )
        resolved = await store.get(created.id, mark_read=False)

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.content.source_path, "D:\\memories\\design")
        self.assertEqual(resolved.tags, ("workspace", "design"))
        self.assertTrue(any(query.startswith("RELATE memory_root:filesystem_memories") for query in database.queries))

    async def test_checkpoint_publication_is_idempotent(self) -> None:
        database = _FakeDatabase()
        store = FilesystemMemoryStore(database)
        memory = FilesystemMemory(
            title="Task checkpoint",
            description="Retained output",
            source_kind="checkpoint",
            backing_store="D:\\Reframe\\workspace-store",
            manifest_id="manifest-one",
            base_memory_ids=("memory_node:project",),
        )

        first = await store.publish_checkpoint("memory_node:manifest_one", memory)
        second = await store.publish_checkpoint("memory_node:manifest_one", memory)

        self.assertEqual(first, second)
        self.assertEqual(
            sum(query.startswith("RELATE memory_root:filesystem_memories") for query in database.queries),
            1,
        )


class _FakeDatabase:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.record = None

    async def query(self, statement, variables=None):
        normalized = statement.strip()
        self.queries.append(normalized)
        if normalized.startswith("CREATE memory_node"):
            now = datetime.now(timezone.utc)
            self.record = {
                "id": "memory_node:filesystem",
                "tags": variables["tags"],
                "content": variables["content"],
                "created_at": now,
                "updated_at": now,
                "read_at": None,
            }
            return [self.record]
        if normalized.startswith("SELECT * FROM memory_root:filesystem_memories"):
            return [self.record] if self.record is not None else []
        return []

    async def mark_records_read(self, records):
        return records


if __name__ == "__main__":
    unittest.main()
