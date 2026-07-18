from __future__ import annotations

from importlib.metadata import distribution
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest import mock

import baml_sdk
import reframe_agent_host
import reframe_memory
from baml_sdk.workspace import ManualWorkspacePlan
from reframe_agent_host.baml_generation import _project_root
from reframe_agent_host.workspace.daemon_process import backing_service_command


def main() -> None:
    host = distribution("reframe-agent-host")
    daemon = distribution("reframe-workspace-daemon")
    requirements = set(host.requires or ())
    expected_baml = (
        "baml-bridge @ git+https://github.com/jubjub727/baml.git"
        "@bbb99a793d707175663c4e9236400a9bcd830f57"
        "#subdirectory=baml_language/sdks/python"
    )
    assert expected_baml in requirements
    assert f"reframe-workspace-daemon=={daemon.version}" in requirements

    environment = Path(sys.prefix).resolve()
    for module in (baml_sdk, reframe_agent_host, reframe_memory):
        assert Path(module.__file__).resolve().is_relative_to(environment)
    assert _project_root() == Path.cwd().resolve()

    plan = ManualWorkspacePlan(
        memory_ids=["memory_node:smoke"],
        prefetch_paths=["README.md"],
        scratch_globs=["tmp/**"],
    )
    assert plan.memory_ids == ["memory_node:smoke"]
    assert plan.rules[0].provenance == "manual"

    executables = [
        Path(daemon.locate_file(entry))
        for entry in daemon.files or ()
        if Path(entry).name
        in {"reframe-workspace-daemon", "reframe-workspace-daemon.exe"}
    ]
    assert len(executables) == 1 and executables[0].is_file()
    executable = executables[0].resolve()
    started = subprocess.run(
        [executable],
        capture_output=True,
        check=False,
        text=True,
    )
    assert started.returncode != 0
    assert "missing backing-service command" in started.stderr

    os.environ.pop("REFRAME_WORKSPACE_DAEMON", None)
    with TemporaryDirectory() as store, mock.patch(
        "reframe_agent_host.workspace.daemon_process.shutil.which",
        return_value=None,
    ):
        command = backing_service_command(Path(store))
    assert Path(command[0]).resolve() == executable
    assert command[1:] == ["--store", store, "serve-socket"]


if __name__ == "__main__":
    main()
