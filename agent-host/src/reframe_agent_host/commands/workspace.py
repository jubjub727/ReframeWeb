from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime
import json
import os

from reframe_agent_host.workspace.coordinator import WorkspaceCoordinator
from reframe_agent_host.workspace.errors import WorkspaceError
from reframe_agent_host.workspace.shortcuts import create_sessions_shortcut


def run_workspace(args) -> int:
    """Run one workspace CLI action through the reusable async coordinator."""
    try:
        result = asyncio.run(run_workspace_async(args))
    except KeyboardInterrupt:
        return 130
    if isinstance(result, int):
        return result
    print(json.dumps(result, indent=2, default=_json_default))
    return 0


async def run_workspace_async(args, coordinator: WorkspaceCoordinator | None = None):
    coordinator = coordinator or WorkspaceCoordinator()
    if args.workspace_area == "memory":
        return await _memory_command(coordinator, args.workspace_action)
    if args.workspace_action == "shortcut":
        shortcut = await asyncio.to_thread(create_sessions_shortcut)
        return {"shortcut": str(shortcut)}

    await coordinator.start()
    try:
        await coordinator.reconcile_pending_publications()
        return await _session_command(coordinator, args)
    finally:
        await coordinator.close()


async def _memory_command(coordinator: WorkspaceCoordinator, action: str):
    if action == "create":
        return _memory_node_json(await coordinator.create_project_memory())
    if action == "list":
        return [_memory_node_json(node) for node in await coordinator.list_memories()]
    raise WorkspaceError(f"unknown filesystem memory action: {action}")


async def _session_command(coordinator: WorkspaceCoordinator, args):
    action = args.workspace_action
    if action == "create":
        created = await coordinator.create_session(
            memory_ids=args.memory,
            continue_session=args.continue_session,
        )
        return created.model_dump()
    if action == "status":
        return (await coordinator.status(args.session)).model_dump()
    if action == "checkpoint":
        checkpoint = await coordinator.checkpoint(
            args.session,
            paths=args.include,
            retain_all=args.all,
        )
        return checkpoint.model_dump()
    if action == "close":
        return _json_value(await coordinator.close_session(args.session))
    if action == "destroy":
        return _json_value(await coordinator.destroy_session(args.session))
    if action == "exec":
        command = list(args.exec_command)
        if command[:1] == ["--"]:
            command = command[1:]
        return await coordinator.run_command(args.session, command)
    if action == "shell":
        return await coordinator.run_command(args.session, [_shell()])
    raise WorkspaceError(f"unknown workspace session action: {action}")


def _memory_node_json(node) -> dict:
    return {
        "id": node.id,
        "tags": list(node.tags),
        "timestamps": asdict(node.timestamps),
        "content": asdict(node.content),
    }


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"cannot encode {type(value).__name__}")


def _json_value(value):
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def _shell() -> str:
    variable = "COMSPEC" if os.name == "nt" else "SHELL"
    return os.getenv(variable, "cmd.exe" if os.name == "nt" else "sh")
