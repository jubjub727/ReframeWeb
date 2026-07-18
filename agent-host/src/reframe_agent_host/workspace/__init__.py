"""Lazy public exports for the Agent Workspace boundary."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from reframe_agent_host.workspace.coordinator import WorkspaceCoordinator
    from reframe_agent_host.workspace.errors import (
        WorkspaceError,
        WorkspaceOutcomeUnknownError,
    )
    from reframe_agent_host.workspace.models import (
        CheckpointMemorySource,
        DaemonCheckpointResult,
        DirectoryMemorySource,
        MemorySource,
        PendingCheckpointPublication,
        PublishedCheckpointResult,
        ResolvedWorkspacePlan,
        WorkspaceCreated,
        WorkspaceStatus,
        WorkspaceSummary,
    )
    from reframe_agent_host.workspace.planning import (
        filesystem_memory_catalog,
        resolve_memory_sources,
        resolve_workspace_plan,
    )
    from reframe_agent_host.workspace.service import WorkspaceDaemon


_EXPORTS = {
    "CheckpointMemorySource": ("reframe_agent_host.workspace.models", None),
    "DaemonCheckpointResult": ("reframe_agent_host.workspace.models", None),
    "DirectoryMemorySource": ("reframe_agent_host.workspace.models", None),
    "MemorySource": ("reframe_agent_host.workspace.models", None),
    "PendingCheckpointPublication": ("reframe_agent_host.workspace.models", None),
    "PublishedCheckpointResult": ("reframe_agent_host.workspace.models", None),
    "ResolvedWorkspacePlan": ("reframe_agent_host.workspace.models", None),
    "WorkspaceCreated": ("reframe_agent_host.workspace.models", None),
    "WorkspaceStatus": ("reframe_agent_host.workspace.models", None),
    "WorkspaceSummary": ("reframe_agent_host.workspace.models", None),
    "WorkspaceError": ("reframe_agent_host.workspace.errors", None),
    "WorkspaceOutcomeUnknownError": ("reframe_agent_host.workspace.errors", None),
    "WorkspaceDaemon": ("reframe_agent_host.workspace.service", None),
    "WorkspaceCoordinator": ("reframe_agent_host.workspace.coordinator", None),
    "filesystem_memory_catalog": ("reframe_agent_host.workspace.planning", None),
    "resolve_memory_sources": ("reframe_agent_host.workspace.planning", None),
    "resolve_workspace_plan": ("reframe_agent_host.workspace.planning", None),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(module_name), attribute or name)
    globals()[name] = value
    return value
