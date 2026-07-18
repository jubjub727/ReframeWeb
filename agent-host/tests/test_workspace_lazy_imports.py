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


if __name__ == "__main__":
    unittest.main()
