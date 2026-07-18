from __future__ import annotations

import asyncio
import unittest

from reframe_memory.config import MemoryConfig
from reframe_memory.database import MemoryDatabase
from reframe_memory.models import DirectoryFilesystemMemory


class FilesystemPublicationIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_transaction_preserves_identity_and_timestamps(self) -> None:
        database = await MemoryDatabase.open(
            MemoryConfig(url="mem://", namespace="publication", database="test")
        )
        try:
            await database.apply_schema()
            await database.filesystem_memories.ensure_root()
            store = database.filesystem_memories
            first_memory = DirectoryFilesystemMemory(
                title="First",
                description="First source",
                source_path="D:/memory/first",
            )
            collision = DirectoryFilesystemMemory(
                title="Collision",
                description="Different source",
                source_path="D:/memory/second",
            )
            record_id = "memory_node:filesystem_transaction_test"

            first = await store._publish(record_id, first_memory, ())  # noqa: SLF001
            await database.mark_record_ids_read([record_id])
            before = await store.get(record_id, mark_read=False)
            assert before is not None

            with self.assertRaisesRegex(ValueError, "filesystem memory id collision"):
                await store._publish(record_id, collision, ())  # noqa: SLF001

            republished = await store._publish(record_id, first_memory, ())  # noqa: SLF001
            self.assertEqual(republished.id, first.id)
            self.assertEqual(republished.timestamps.created_at, before.timestamps.created_at)
            self.assertEqual(republished.timestamps.updated_at, before.timestamps.updated_at)
            self.assertEqual(republished.timestamps.read_at, before.timestamps.read_at)

            await asyncio.sleep(0.001)
            changed_memory = DirectoryFilesystemMemory(
                title="Renamed",
                description="Updated source description",
                source_path=first_memory.source_path,
            )
            changed = await store._publish(  # noqa: SLF001
                record_id,
                changed_memory,
                ("updated",),
            )

            self.assertEqual(changed.content, changed_memory)
            self.assertEqual(changed.tags, ("updated",))
            self.assertEqual(changed.timestamps.created_at, before.timestamps.created_at)
            self.assertEqual(changed.timestamps.read_at, before.timestamps.read_at)
            self.assertGreater(
                changed.timestamps.updated_at,
                republished.timestamps.updated_at,
            )
        finally:
            await database.close()


if __name__ == "__main__":
    unittest.main()
