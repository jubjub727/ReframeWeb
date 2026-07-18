from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from reframe_agent_host.workspace.memory_service import (
        WorkspaceMemoryService,
        WorkspacePlanFunction,
    )
    from reframe_agent_host.workspace.publication_service import CheckpointPublisher
    from reframe_agent_host.workspace.service import WorkspaceDaemon
    from reframe_memory import MemoryDatabase


DatabaseFactory = Callable[[], Awaitable["MemoryDatabase"]]
CheckpointFunction = Callable[..., Awaitable[Any]]


async def _open_default_memory_database() -> MemoryDatabase:
    from reframe_memory import open_memory_database

    return await open_memory_database()


class WorkspaceCoordinatorServices:
    """Lazily loads graph and BAML services outside the session command path."""

    def __init__(
        self,
        daemon: WorkspaceDaemon,
        database_factory: DatabaseFactory | None,
        workspace_plan: WorkspacePlanFunction | None,
        checkpoint_selection: CheckpointFunction | None,
    ) -> None:
        self._daemon = daemon
        self._database_factory = database_factory
        self._workspace_plan = workspace_plan
        self._checkpoint_selection = checkpoint_selection
        self._publisher: CheckpointPublisher | None = None
        self._memories: WorkspaceMemoryService | None = None

    def memory_service(self) -> WorkspaceMemoryService:
        if self._memories is None:
            from baml_sdk.workspace import ManualWorkspacePlan_async
            from reframe_agent_host.workspace.memory_service import (
                WorkspaceMemoryService,
            )

            plan = self._workspace_plan or ManualWorkspacePlan_async
            self._memories = WorkspaceMemoryService(
                self._resolved_database_factory(),
                plan,
            )
        return self._memories

    def checkpoint_publisher(self) -> CheckpointPublisher:
        if self._publisher is None:
            from reframe_agent_host.workspace.publication_service import (
                CheckpointPublisher,
            )

            self._publisher = CheckpointPublisher(
                self._daemon,
                self._resolved_database_factory(),
            )
        return self._publisher

    def checkpoint_function(self) -> CheckpointFunction:
        if self._checkpoint_selection is None:
            from baml_sdk.workspace import ManualCheckpoint_async

            self._checkpoint_selection = ManualCheckpoint_async
        return self._checkpoint_selection

    def _resolved_database_factory(self) -> DatabaseFactory:
        if self._database_factory is None:
            self._database_factory = _open_default_memory_database
        return self._database_factory
