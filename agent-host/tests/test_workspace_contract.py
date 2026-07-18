from __future__ import annotations

from contextlib import suppress
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from reframe_agent_host.workspace.models import (
    CheckpointMemorySource,
    DirectoryMemorySource,
)
from reframe_agent_host.workspace.protocol import PROTOCOL_VERSION
from reframe_agent_host.workspace.service import WorkspaceDaemon


@unittest.skipUnless(
    os.getenv("REFRAME_WORKSPACE_DAEMON"),
    "REFRAME_WORKSPACE_DAEMON is required for the Python/Rust contract test",
)
class WorkspaceDaemonContractTests(unittest.TestCase):
    def test_typed_client_and_rust_daemon_share_the_wire_contract(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = root / "store"
            source = root / "source"
            source.mkdir()
            (source / "source.txt").write_text("source memory\n", encoding="utf-8")
            directory_memory = DirectoryMemorySource(
                memory_id="memory:contract-source",
                source_path=str(source),
            )
            daemon = WorkspaceDaemon(store)
            stopped = False
            try:
                daemon.start()
                hello = daemon.hello()
                health = daemon.health()
                created = daemon.create_workspace(
                    name="Contract smoke test",
                    session_id="contract-session",
                    memory_sources=[directory_memory],
                    scratch_paths=[],
                )
                result_path = Path(created.worktree) / "result.txt"
                result_path.write_text("checkpoint result\n", encoding="utf-8")
                dirty_status = daemon.get_workspace_status(created.session_id)
                checkpoint = daemon.commit_checkpoint(
                    created.session_id,
                    paths=["result.txt"],
                    all=False,
                )
                pending = daemon.list_pending_checkpoint_publications()
                publication = daemon.complete_checkpoint_publication(
                    checkpoint.manifest_id,
                    "memory:contract-checkpoint",
                )
                continued = daemon.create_workspace(
                    name="Contract checkpoint source",
                    session_id="contract-continuation",
                    memory_sources=[
                        CheckpointMemorySource(
                            memory_id="memory:contract-checkpoint",
                            backing_store=str(store),
                            manifest_id=checkpoint.manifest_id,
                        )
                    ],
                    scratch_paths=[],
                )
                summaries = daemon.list_workspaces(active_only=False)
                status = daemon.get_workspace_status(created.session_id)

                self.assertEqual(hello.protocol_version, PROTOCOL_VERSION)
                self.assertEqual(health.status, "ready")
                self.assertEqual(created.session_id, "contract-session")
                self.assertEqual(created.memory_ids, [directory_memory.memory_id])
                self.assertEqual(created.projected_files, 1)
                self.assertIn(
                    ("result.txt", "create"),
                    {(change.path, change.kind) for change in dirty_status.changes},
                )
                self.assertEqual(
                    [item.manifest_id for item in pending],
                    [checkpoint.manifest_id],
                )
                self.assertTrue(publication.published)
                self.assertEqual(
                    daemon.list_pending_checkpoint_publications(),
                    [],
                )
                self.assertEqual(
                    continued.memory_ids,
                    ["memory:contract-checkpoint"],
                )
                self.assertGreaterEqual(continued.projected_files, 1)
                self.assertEqual(summaries[0].session_id, continued.session_id)
                self.assertEqual(status.session_id, created.session_id)
                self.assertEqual(status.head_manifest, checkpoint.manifest_id)
                shutdown = daemon.shutdown()
                stopped = True
                self.assertTrue(shutdown.shutdown)
            finally:
                if not stopped:
                    with suppress(Exception):
                        daemon.shutdown()
                daemon.close()


if __name__ == "__main__":
    unittest.main()
