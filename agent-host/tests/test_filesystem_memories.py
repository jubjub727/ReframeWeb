from __future__ import annotations

from datetime import datetime, timezone
import re
from tempfile import TemporaryDirectory
import unittest

from reframe_memory import (
    CheckpointFilesystemMemory,
    DirectoryFilesystemMemory,
    FilesystemMemory,
)
from reframe_memory.filesystem_memories import (
    FilesystemMemoryStore,
    filesystem_checkpoint_memory_id,
    filesystem_directory_memory_id,
)


class FilesystemMemoryStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_and_resolve_canonical_directory_memory(self) -> None:
        database = _FakeDatabase()
        store = FilesystemMemoryStore(database)
        memory = DirectoryFilesystemMemory(
            title="Design",
            description="Project decisions",
            source_path="D:\\memories\\design",
        )

        created = await store.publish_directory(
            memory,
            tags=("workspace", "design"),
        )
        resolved = await store.get(created.id, mark_read=False)

        self.assertEqual(created.id, filesystem_directory_memory_id(memory.source_path))
        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.content.source_path, "D:\\memories\\design")
        self.assertEqual(resolved.tags, ("workspace", "design"))
        self.assertTrue(
            any(
                "RELATE memory_root:filesystem_memories" in query
                for query in database.queries
            )
        )
        transaction = next(
            query
            for query in database.queries
            if "UPSERT memory_node:filesystem_directory_" in query
        )
        self.assertIn("BEGIN TRANSACTION", transaction)
        self.assertIn("RELATE memory_root:filesystem_memories", transaction)
        self.assertIn("COMMIT TRANSACTION", transaction)

    def test_base_filesystem_memory_cannot_be_instantiated(self) -> None:
        with self.assertRaises(TypeError):
            FilesystemMemory(title="Abstract", description="Not persistable")

    async def test_checkpoint_publication_is_idempotent(self) -> None:
        database = _FakeDatabase()
        store = FilesystemMemoryStore(database)
        memory = CheckpointFilesystemMemory(
            title="Task checkpoint",
            description="Retained output",
            backing_store="D:\\Reframe\\workspace-store",
            manifest_id="manifest-one",
            base_memory_ids=("memory_node:project",),
        )

        first = await store.publish_checkpoint(memory)
        second = await store.publish_checkpoint(memory)

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.content, second.content)
        self.assertEqual(
            sum("UPSERT memory_node:filesystem_checkpoint_" in query for query in database.queries),
            2,
        )
        publication_queries = [
            query
            for query in database.queries
            if "UPSERT memory_node:filesystem_checkpoint_" in query
        ]
        self.assertTrue(
            all("DELETE contains" in query and "RELATE memory_root" in query for query in publication_queries)
        )
        self.assertTrue(
            all(
                "LET $existing = SELECT * FROM ONLY" in query
                and "LET $identity_conflicts" in query
                and "created_at = IF $existing = NONE" in query
                for query in publication_queries
            )
        )

    async def test_publication_rejects_an_atomic_identity_collision(self) -> None:
        database = _FakeDatabase()
        store = FilesystemMemoryStore(database)
        first = DirectoryFilesystemMemory(
            title="First",
            description="First source",
            source_path="D:\\memories\\first",
        )
        second = DirectoryFilesystemMemory(
            title="Second",
            description="Second source",
            source_path="D:\\memories\\second",
        )

        await store._publish("memory_node:filesystem_collision", first, ())  # noqa: SLF001
        with self.assertRaisesRegex(ValueError, "filesystem memory id collision"):
            await store._publish("memory_node:filesystem_collision", second, ())  # noqa: SLF001

    def test_checkpoint_identity_is_store_scoped_and_collision_safe(self) -> None:
        with TemporaryDirectory() as first, TemporaryDirectory() as second:
            first_id = filesystem_checkpoint_memory_id(first, "manifest-a_b")
            punctuation_id = filesystem_checkpoint_memory_id(first, "manifest-a-b")
            second_store_id = filesystem_checkpoint_memory_id(second, "manifest-a_b")

        self.assertNotEqual(first_id, punctuation_id)
        self.assertNotEqual(first_id, second_store_id)
        self.assertRegex(first_id, r"^memory_node:filesystem_checkpoint_[0-9a-f]{64}$")


class _FakeDatabase:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.record = None

    async def query(self, statement, variables=None):
        normalized = statement.strip()
        self.queries.append(normalized)
        if "UPSERT memory_node:filesystem_" in normalized:
            record_id = re.search(
                r"UPSERT (memory_node:[A-Za-z0-9_-]+)", normalized
            ).group(1)
            now = datetime.now(timezone.utc)
            existing_identity = (
                self.record.get("filesystem_identity") if self.record else None
            )
            if existing_identity is not None and existing_identity != variables["identity"]:
                return []
            created_at = self.record["created_at"] if self.record else now
            read_at = self.record["read_at"] if self.record else None
            self.record = {
                "id": record_id,
                "tags": variables["tags"],
                "content": variables["content"],
                "filesystem_identity": variables["identity"],
                "created_at": created_at,
                "updated_at": now,
                "read_at": read_at,
            }
            return []
        if normalized.startswith("SELECT * FROM memory_node:"):
            record_id = normalized.split()[3]
            return [self.record] if self.record and self.record["id"] == record_id else []
        if normalized.startswith("SELECT * FROM memory_root:filesystem_memories"):
            return [self.record] if self.record is not None else []
        return []

    async def mark_records_read(self, records):
        return records


if __name__ == "__main__":
    unittest.main()
