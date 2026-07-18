from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from baml_sdk.workspace import (
    ManualCheckpoint_async,
    ManualWorkspacePlan_async,
)
from reframe_agent_host.workspace.execution import run_in_workspace
from reframe_agent_host.workspace.errors import WorkspaceError
from reframe_agent_host.workspace.memory_service import (
    WorkspaceMemoryService,
    WorkspacePlanFunction,
)
from reframe_agent_host.workspace.models import (
    DaemonCheckpointResult,
    PublishedCheckpointResult,
    WorkspaceCreated,
    WorkspaceStatus,
    WorkspaceSummary,
)
from reframe_agent_host.workspace.publication_service import (
    CheckpointPublication,
    CheckpointPublisher,
)
from reframe_agent_host.workspace.service import WorkspaceDaemon
from reframe_memory import (
    FilesystemMemoryNode,
    MemoryDatabase,
    open_memory_database,
)


DatabaseFactory = Callable[[], Awaitable[MemoryDatabase]]
CheckpointFunction = Callable[..., Awaitable[Any]]


class WorkspaceCoordinator:
    """Async application boundary for workspace and graph-memory orchestration."""

    def __init__(
        self,
        daemon: WorkspaceDaemon | None = None,
        *,
        database_factory: DatabaseFactory = open_memory_database,
        workspace_plan: WorkspacePlanFunction = ManualWorkspacePlan_async,
        checkpoint_selection: CheckpointFunction = ManualCheckpoint_async,
    ) -> None:
        self.daemon = daemon or WorkspaceDaemon()
        self._publisher = CheckpointPublisher(self.daemon, database_factory)
        self._memories = WorkspaceMemoryService(database_factory, workspace_plan)
        self._checkpoint_selection = checkpoint_selection

    async def start(self) -> None:
        await asyncio.to_thread(self.daemon.start)

    async def close(self) -> None:
        await asyncio.to_thread(self.daemon.close)

    async def create_project_memory(self) -> FilesystemMemoryNode:
        return await self._memories.create_project_memory()

    async def list_memories(self) -> list[FilesystemMemoryNode]:
        return await self._memories.list_memories()

    async def create_session(
        self,
        *,
        memory_ids: Sequence[str],
        continue_session: str | None,
    ) -> WorkspaceCreated:
        if memory_ids and continue_session is not None:
            raise WorkspaceError("--memory cannot be combined with --continue")
        inherited = await self._continue_target(continue_session)
        selected = list(memory_ids) or inherited
        resolved = await self._memories.resolve_plan(selected)
        value = await self._daemon_call(
            "create_workspace",
            name="Agent task session",
            session_id=None,
            memory_sources=resolved.memory_sources,
            scratch_paths=resolved.scratch_paths,
        )
        created = _model(WorkspaceCreated, value)
        if resolved.prefetch_paths:
            try:
                await self._prefetch_session(
                    created.session_id,
                    resolved.prefetch_paths,
                )
            except Exception as error:
                raise WorkspaceError(
                    f"workspace session {created.session_id} was durably created, "
                    "but its prefetch lifecycle failed; it remains active and "
                    f"recoverable: {error}"
                ) from error
        return created

    async def status(self, requested: str | None) -> WorkspaceStatus:
        session_id = await self.select_session(requested, require_active=False)
        value = await self._daemon_call("get_workspace_status", session_id=session_id)
        return _model(WorkspaceStatus, value)

    async def checkpoint(
        self,
        requested: str | None,
        *,
        paths: Sequence[str],
        retain_all: bool,
    ) -> PublishedCheckpointResult:
        session_id = await self.select_session(requested, require_active=True)
        selection = await self._checkpoint_selection(list(paths))
        value = await self._daemon_call(
            "commit_checkpoint",
            session_id=session_id,
            paths=list(selection.paths),
            all=retain_all,
        )
        checkpoint = _model(DaemonCheckpointResult, value)
        try:
            memory = await self._publisher.publish_manifest(checkpoint.manifest_id)
        except Exception as error:
            raise WorkspaceError(
                f"checkpoint {checkpoint.manifest_id} committed; memory publication "
                f"remains pending in the daemon outbox: {error}"
            ) from error
        return PublishedCheckpointResult(
            **checkpoint.model_dump(),
            memory_id=memory.id,
        )

    async def close_session(self, requested: str | None) -> Any:
        session_id = await self.select_session(requested, require_active=True)
        return await self._daemon_call("close_workspace", session_id=session_id)

    async def destroy_session(self, requested: str | None) -> Any:
        session_id = await self.select_session(requested, require_active=False)
        return await self._daemon_call(
            "destroy_ephemeral_workspace",
            session_id=session_id,
        )

    async def run_command(
        self,
        requested: str | None,
        command: Sequence[str],
    ) -> int:
        session_id = await self.select_session(requested, require_active=True)
        return await run_in_workspace(self.daemon, session_id, command)

    async def select_session(
        self,
        requested: str | None,
        *,
        require_active: bool,
    ) -> str:
        if requested is not None:
            return requested
        latest = await self.latest_summary(require_active=require_active)
        return latest.session_id

    async def latest_summary(self, *, require_active: bool) -> WorkspaceSummary:
        summaries = await self._summaries()
        if not summaries:
            raise WorkspaceError("no workspace session exists")
        latest = summaries[0]
        if require_active and latest.state != "active":
            raise WorkspaceError(
                f"latest workspace session is closed: {latest.session_id}; "
                "create a new session"
            )
        return latest

    async def summary_for(self, session_id: str) -> WorkspaceSummary:
        for summary in await self._summaries():
            if summary.session_id == session_id:
                return summary
        raise WorkspaceError(f"workspace session does not exist: {session_id}")

    async def reconcile_pending_publications(self, *, strict: bool = False) -> int:
        return await self._publisher.reconcile(strict=strict)

    async def _continue_target(self, requested: str | None) -> list[str]:
        if requested is None:
            return []
        summary = (
            await self.latest_summary(require_active=False)
            if requested == "latest"
            else await self.summary_for(requested)
        )
        if summary.head_manifest is None:
            raise WorkspaceError(
                f"session has no checkpoint to continue: {summary.session_id}"
            )
        publication = CheckpointPublication(
            session_id=summary.session_id,
            session_name=summary.name,
            backing_store=str(self.daemon.store),
            manifest_id=summary.head_manifest,
            base_memory_ids=tuple(summary.memory_ids),
            retained_count=None,
        )
        memory = await self._publisher.publish_external(publication)
        return [memory.id]

    async def _summaries(self) -> list[WorkspaceSummary]:
        values = await self._daemon_call("list_workspaces", active_only=False)
        return [_model(WorkspaceSummary, value) for value in values]

    async def _prefetch_session(
        self,
        session_id: str,
        paths: Sequence[str],
    ) -> None:
        await self._daemon_call("mount_workspace", session_id=session_id)
        try:
            await self._daemon_call("prefetch", session_id=session_id, paths=paths)
        finally:
            await self._daemon_call("unmount_workspace", session_id=session_id)

    async def _daemon_call(self, method: str, **arguments: Any) -> Any:
        operation = getattr(self.daemon, method)
        return await asyncio.to_thread(operation, **arguments)


def _model(model_type, value):
    return value if isinstance(value, model_type) else model_type.model_validate(value)
