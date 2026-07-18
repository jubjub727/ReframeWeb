from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import time
from typing import Any, TextIO

from reframe_agent_host.workspace.errors import WorkspaceError


_DIAGNOSTIC_LOG_LIMIT = 1024 * 1024
_DIAGNOSTIC_TAIL_BYTES = 8 * 1024


def backing_service_command(store: Path) -> list[str]:
    configured = os.getenv("REFRAME_WORKSPACE_DAEMON")
    if configured:
        executable = Path(configured).expanduser().resolve()
        if not executable.is_file():
            raise WorkspaceError(f"workspace backing service does not exist: {executable}")
        return [str(executable), "--store", str(store), "serve-socket"]

    binary = shutil.which("reframe-workspace-daemon")
    if binary is None:
        binary = _adjacent_backing_service()
    if binary is None:
        raise WorkspaceError(
            "workspace backing service is not installed; run 'uv sync' in agent-host"
        )
    return [binary, "--store", str(store), "serve-socket"]


def _adjacent_backing_service() -> str | None:
    name = (
        "reframe-workspace-daemon.exe"
        if os.name == "nt"
        else "reframe-workspace-daemon"
    )
    directories = (
        Path(sys.executable).parent,
        Path(sysconfig.get_path("scripts")),
    )
    for directory in dict.fromkeys(directories):
        candidate = directory / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
    return None


def launch_service(store: Path) -> tuple[subprocess.Popen[bytes], Path]:
    command = backing_service_command(store)
    log_path = store / "workspace-daemon.log"
    log = _open_diagnostic_log(log_path)
    try:
        log.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] launching workspace daemon\n")
        log.flush()
        options: dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": log,
            "stderr": subprocess.STDOUT,
            "close_fds": True,
        }
        if os.name == "nt":
            options["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NO_WINDOW
            )
        else:
            options["start_new_session"] = True
        return subprocess.Popen(command, **options), log_path
    finally:
        log.close()


def startup_diagnostics(log_path: Path | None) -> str | None:
    if log_path is None:
        return None
    try:
        with log_path.open("rb") as log:
            log.seek(0, os.SEEK_END)
            size = log.tell()
            log.seek(max(0, size - _DIAGNOSTIC_TAIL_BYTES))
            tail = log.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return None
    return tail or None


def _open_diagnostic_log(path: Path) -> TextIO:
    if path.exists() and path.stat().st_size > _DIAGNOSTIC_LOG_LIMIT:
        rotated = path.with_suffix(".previous.log")
        try:
            path.replace(rotated)
        except OSError:
            pass
    return path.open("a", encoding="utf-8")
