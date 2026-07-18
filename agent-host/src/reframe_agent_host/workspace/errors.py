from __future__ import annotations

from reframe_agent_host.workspace.protocol import WorkspaceProtocolError


class WorkspaceError(RuntimeError):
    """Base exception for the typed workspace service boundary."""


class WorkspaceTransportError(WorkspaceError):
    """The local daemon connection failed before a response was received."""


class WorkspaceOutcomeUnknownError(WorkspaceTransportError):
    """A process-local mutation may have completed before transport failure."""


class WorkspaceRemoteError(WorkspaceError):
    """A structured error returned by the workspace daemon."""

    def __init__(self, detail: WorkspaceProtocolError) -> None:
        super().__init__(f"{detail.code}: {detail.message}")
        self.detail = detail
