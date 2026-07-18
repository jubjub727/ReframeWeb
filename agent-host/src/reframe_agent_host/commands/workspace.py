from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess

from reframe_agent_host.workspace import (
    CheckpointResult,
    WorkspaceCreated,
    WorkspaceDaemon,
    WorkspaceError,
    WorkspaceStatus,
    WorkspaceSummary,
    resolve_memory_sources,
)
from reframe_agent_host.workspace.location import project_root
from reframe_agent_host.workspace.models import MountedWorkspace
from reframe_agent_host.workspace.shortcuts import create_sessions_shortcut
from reframe_memory import FilesystemMemory, MemoryDatabase, open_memory_database


def run_workspace(args) -> int:
    if args.workspace_area == "memory":
        result = asyncio.run(_memory_command(args))
        print(json.dumps(result, indent=2, default=_json_default))
        return 0
    if args.workspace_action == "shortcut":
        result = {"shortcut": str(create_sessions_shortcut())}
        print(json.dumps(result, indent=2))
        return 0
    with WorkspaceDaemon() as daemon:
        if args.workspace_action == "create":
            inherited_memories = _continue_target(
                daemon,
                args.continue_session,
            )
            memory_sources = asyncio.run(
                _resolve_memory_sources(args.memory, inherited_memories)
            )
            result = _session_command(
                daemon,
                args,
                session_id=None,
                memory_sources=memory_sources,
            )
        else:
            active_only = args.workspace_action in {"exec", "shell", "checkpoint", "close"}
            session_id = _select_session(daemon, args.session, active_only=active_only)
            result = _session_command(
                daemon,
                args,
                session_id=session_id,
                memory_sources=[],
            )
    if isinstance(result, int):
        return result
    print(json.dumps(result, indent=2))
    return 0


def _session_command(
    daemon: WorkspaceDaemon,
    args,
    *,
    session_id: str | None,
    memory_sources,
):
    action = args.workspace_action
    if action == "create":
        return WorkspaceCreated.model_validate(
            daemon.request(
                "create_workspace",
                name="Agent task session",
                session_id=None,
                memory_sources=memory_sources,
                scratch_paths=[],
            )
        ).model_dump()
    if session_id is None:
        raise WorkspaceError("session selection failed")
    if action == "status":
        return WorkspaceStatus.model_validate(
            daemon.request("get_workspace_status", session_id=session_id)
        ).model_dump()
    if action == "checkpoint":
        summary = _summary_for(daemon, session_id)
        checkpoint = CheckpointResult.model_validate(
            daemon.request(
                "commit_checkpoint",
                session_id=session_id,
                paths=args.include,
                all=args.all,
            )
        )
        memory = asyncio.run(
            _publish_checkpoint_memory(
                daemon,
                summary,
                checkpoint.manifest_id,
                len(checkpoint.retained_paths),
            )
        )
        return checkpoint.model_copy(update={"memory_id": memory.id}).model_dump()
    if action == "close":
        return daemon.request("close_workspace", session_id=session_id)
    if action == "destroy":
        return daemon.request(
            "destroy_ephemeral_workspace",
            session_id=session_id,
        )
    if action == "exec":
        command = list(args.exec_command)
        if command[:1] == ["--"]:
            command = command[1:]
        if not command:
            raise WorkspaceError("workspace session exec requires a command after '--'")
        return _run_mounted(daemon, session_id, command)
    if action == "shell":
        return _run_mounted(daemon, session_id, [_shell()])
    raise WorkspaceError(f"unknown workspace session action: {action}")


async def _memory_command(args):
    database = await open_memory_database()
    try:
        await database.apply_schema()
        await database.filesystem_memories.ensure_root()
        if args.workspace_action == "create":
            return _memory_node_json(await _ensure_project_memory(database))
        if args.workspace_action == "list":
            nodes = await database.filesystem_memories.list()
            return [_memory_node_json(node) for node in nodes]
        raise WorkspaceError(f"unknown filesystem memory action: {args.workspace_action}")
    finally:
        await database.close()


async def _resolve_memory_sources(
    requested_ids: list[str],
    inherited_ids: list[str],
) -> list[dict[str, str]]:
    memory_ids = requested_ids or inherited_ids
    if not memory_ids:
        return []
    database = await open_memory_database()
    try:
        sources = await resolve_memory_sources(database, memory_ids)
        return [source.model_dump() for source in sources]
    finally:
        await database.close()


def _memory_node_json(node) -> dict:
    return {
        "id": node.id,
        "tags": list(node.tags),
        "timestamps": asdict(node.timestamps),
        "content": asdict(node.content),
    }


async def _ensure_project_memory(database: MemoryDatabase):
    source = project_root()
    existing = await database.filesystem_memories.list()
    for node in existing:
        if (
            node.content.source_kind == "directory"
            and node.content.source_path is not None
            and Path(node.content.source_path).resolve() == source
        ):
            return node
    return await database.filesystem_memories.create(
        FilesystemMemory(
            title=source.name,
            description=f"Filesystem memory for the {source.name} project",
            source_kind="directory",
            source_path=str(source),
        ),
        tags=("workspace",),
    )


async def _publish_checkpoint_memory(
    daemon: WorkspaceDaemon,
    summary: WorkspaceSummary,
    manifest_id: str,
    retained_count: int | None = None,
):
    database = await open_memory_database()
    try:
        await database.apply_schema()
        await database.filesystem_memories.ensure_root()
        count = "selected files" if retained_count is None else f"{retained_count} retained files"
        memory = FilesystemMemory(
            title=f"{summary.name} checkpoint",
            description=f"Immutable session checkpoint containing {count}",
            source_kind="checkpoint",
            backing_store=str(daemon.store),
            manifest_id=manifest_id,
            base_memory_ids=tuple(summary.memory_ids),
        )
        return await database.filesystem_memories.publish_checkpoint(
            _checkpoint_memory_id(manifest_id),
            memory,
            tags=("workspace", "checkpoint", "session-filesystem"),
        )
    finally:
        await database.close()


def _checkpoint_memory_id(manifest_id: str) -> str:
    safe_id = "".join(
        character if character.isalnum() or character == "_" else "_"
        for character in manifest_id
    )
    return f"memory_node:{safe_id}"


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"cannot encode {type(value).__name__}")


def _run_mounted(
    daemon: WorkspaceDaemon,
    session_id: str,
    command: list[str],
) -> int:
    mounted = MountedWorkspace.model_validate(
        daemon.request("mount_workspace", session_id=session_id)
    )
    mount_path = Path(mounted.mount_path)
    try:
        process = subprocess.Popen(command, cwd=mount_path)
        try:
            return process.wait()
        except KeyboardInterrupt:
            process.terminate()
            process.wait()
            return 130
    finally:
        daemon.request("unmount_workspace", session_id=session_id)


def _shell() -> str:
    variable = "COMSPEC" if os.name == "nt" else "SHELL"
    return os.getenv(variable, "cmd.exe" if os.name == "nt" else "sh")


def _continue_target(
    daemon: WorkspaceDaemon,
    requested: str | None,
) -> list[str]:
    if requested is None:
        return []
    summary = (
        _latest_summary(daemon, active_only=False)
        if requested == "latest"
        else _summary_for(daemon, requested)
    )
    if summary.head_manifest is None:
        raise WorkspaceError(f"session has no checkpoint to continue: {summary.session_id}")
    memory = asyncio.run(
        _publish_checkpoint_memory(daemon, summary, summary.head_manifest)
    )
    return [memory.id]


def _select_session(
    daemon: WorkspaceDaemon,
    requested: str | None,
    *,
    active_only: bool,
) -> str:
    if requested is not None:
        return requested
    return _latest_summary(daemon, active_only=active_only).session_id


def _latest_summary(
    daemon: WorkspaceDaemon,
    *,
    active_only: bool,
) -> WorkspaceSummary:
    summaries = [
        WorkspaceSummary.model_validate(value)
        for value in daemon.request("list_workspaces", active_only=False)
    ]
    if not summaries:
        raise WorkspaceError("no workspace session exists")
    latest = summaries[0]
    if active_only and latest.state != "active":
        raise WorkspaceError(
            f"latest workspace session is closed: {latest.session_id}; create a new session"
        )
    return latest


def _summary_for(daemon: WorkspaceDaemon, session_id: str) -> WorkspaceSummary:
    summaries = [
        WorkspaceSummary.model_validate(value)
        for value in daemon.request("list_workspaces", active_only=False)
    ]
    for summary in summaries:
        if summary.session_id == session_id:
            return summary
    raise WorkspaceError(f"workspace session does not exist: {session_id}")
