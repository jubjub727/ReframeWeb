from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

from reframe_agent_host.workspace.models import MountedWorkspace
from reframe_agent_host.workspace.errors import WorkspaceError


async def run_in_workspace(
    daemon,
    session_id: str,
    command: Sequence[str],
) -> int:
    if not command:
        raise WorkspaceError("workspace session exec requires a command after '--'")
    mounted_value = await asyncio.to_thread(
        daemon.mount_workspace,
        session_id=session_id,
    )
    mounted = (
        mounted_value
        if isinstance(mounted_value, MountedWorkspace)
        else MountedWorkspace.model_validate(mounted_value)
    )
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=Path(mounted.mount_path),
        )
        try:
            return await process.wait()
        except asyncio.CancelledError:
            process.terminate()
            await process.wait()
            return 130
    finally:
        await asyncio.to_thread(
            daemon.unmount_workspace,
            session_id=session_id,
        )
