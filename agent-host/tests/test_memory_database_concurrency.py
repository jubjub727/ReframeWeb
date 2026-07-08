import asyncio
import unittest
from unittest.mock import patch

from reframe_memory import MemoryConfig
from reframe_memory.database import _SurrealKvWorker


class FakeSurreal:
    instances = []

    def __init__(self, url):
        self.url = url
        self.active = 0
        self.max_active = 0
        self.calls = []
        FakeSurreal.instances.append(self)

    async def connect(self):
        return None

    async def use(self, namespace, database):
        self.namespace = namespace
        self.database = database

    async def close(self):
        return None

    async def query(self, statement, variables=None):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.01)
            self.calls.append((statement, variables))
            return [{"statement": statement}]
        finally:
            self.active -= 1


class MemoryDatabaseConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_surrealkv_worker_queues_concurrent_queries_on_one_client(self):
        FakeSurreal.instances = []
        with patch("reframe_memory.database.AsyncSurreal", FakeSurreal):
            worker = _SurrealKvWorker(MemoryConfig(url="surrealkv://test"))
            results = await asyncio.gather(
                worker.query("SELECT 1"),
                worker.query("SELECT 2"),
            )

        self.assertEqual(len(FakeSurreal.instances), 1)
        client = FakeSurreal.instances[0]
        self.assertEqual(client.max_active, 1)
        self.assertEqual(
            sorted(call[0] for call in client.calls),
            ["SELECT 1", "SELECT 2"],
        )
        self.assertEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()
