from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

from reframe_agent_host.workspace.location import project_root
from reframe_agent_host.workspace.service import WorkspaceError, default_store


def create_sessions_shortcut(
    *,
    repository: Path | None = None,
    sessions: Path | None = None,
    platform: str | None = None,
) -> Path:
    repository = (repository or project_root()).resolve()
    sessions = (sessions or default_store() / "sessions").resolve()
    sessions.mkdir(parents=True, exist_ok=True)
    platform = platform or sys.platform
    if platform == "win32":
        shortcut = repository / "Agent Sessions.lnk"
        _create_windows_shortcut(shortcut, sessions)
    else:
        shortcut = repository / "Agent Sessions"
        _create_directory_link(shortcut, sessions)
    return shortcut


def _create_directory_link(shortcut: Path, sessions: Path) -> None:
    if shortcut.is_symlink():
        if shortcut.resolve() == sessions:
            return
        shortcut.unlink()
    elif shortcut.exists():
        raise WorkspaceError(f"shortcut path already exists: {shortcut}")
    shortcut.symlink_to(sessions, target_is_directory=True)


def _create_windows_shortcut(shortcut: Path, sessions: Path) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        raise WorkspaceError("PowerShell is required to create a Windows shortcut")
    explorer = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "explorer.exe"
    quoted_sessions = f'"{sessions}"'
    script = ";".join(
        (
            "$shell=New-Object -ComObject WScript.Shell",
            f"$link=$shell.CreateShortcut({_powershell_literal(shortcut)})",
            f"$link.TargetPath={_powershell_literal(explorer)}",
            f"$link.Arguments={_powershell_literal(quoted_sessions)}",
            f"$link.WorkingDirectory={_powershell_literal(sessions)}",
            f"$link.IconLocation={_powershell_literal(f'{explorer},0')}",
            "$link.Description='Browse Reframe agent workspace sessions'",
            "$link.Save()",
        )
    )
    subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
    )


def _powershell_literal(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"
