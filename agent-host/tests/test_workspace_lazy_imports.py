from __future__ import annotations

import subprocess
import sys
import unittest


class WorkspaceLazyImportTests(unittest.TestCase):
    def test_protocol_import_does_not_load_baml_runtime(self) -> None:
        script = """
import sys
import reframe_agent_host.workspace.protocol
assert 'baml_sdk' not in sys.modules
assert 'baml_bridge' not in sys.modules
"""
        subprocess.run([sys.executable, "-c", script], check=True)

    def test_workspace_cli_fast_path_skips_unrelated_runtimes(self) -> None:
        script = """
import sys
from unittest import mock

import reframe_agent_host.cli as cli

with mock.patch(
    'reframe_agent_host.commands.workspace.run_workspace',
    return_value=0,
):
    try:
        cli._main(['workspace', 'session', 'status', '--session', 'task'])
    except SystemExit as error:
        assert error.code == 0

assert 'reframe_agent_host.commands.parser' not in sys.modules
assert 'baml_sdk' not in sys.modules
assert 'baml_bridge' not in sys.modules
assert 'reframe_memory' not in sys.modules
assert 'surrealdb' not in sys.modules
"""
        subprocess.run([sys.executable, "-c", script], check=True)

    def test_empty_outbox_check_does_not_load_graph_or_baml(self) -> None:
        script = """
import asyncio
import sys
from pathlib import Path

from reframe_agent_host.workspace.coordinator import WorkspaceCoordinator

class Daemon:
    store = Path('unused')

    def list_pending_checkpoint_publications(self):
        return []

coordinator = WorkspaceCoordinator(Daemon())
assert asyncio.run(coordinator.reconcile_pending_publications()) == 0
assert 'baml_sdk' not in sys.modules
assert 'baml_bridge' not in sys.modules
assert 'reframe_memory' not in sys.modules
assert 'surrealdb' not in sys.modules
"""
        subprocess.run([sys.executable, "-c", script], check=True)


if __name__ == "__main__":
    unittest.main()
