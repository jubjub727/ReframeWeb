from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, model_validator


PROTOCOL_VERSION = 2
MAX_FRAME_BYTES = 16 * 1024 * 1024
REQUIRED_CAPABILITIES: Final[frozenset[str]] = frozenset(
    {
        "framed-json-v1",
        "idempotent-mutations",
        "idempotency-scopes",
        "operation-metadata",
        "structured-errors",
    }
)


class WorkspaceOperation(StrEnum):
    HELLO = "hello"
    HEALTH = "health"
    CREATE_WORKSPACE = "create_workspace"
    APPLY_POLICY = "apply_policy"
    MOUNT_WORKSPACE = "mount_workspace"
    PREFETCH = "prefetch"
    GET_CHANGE_JOURNAL = "get_change_journal"
    GET_WORKSPACE_STATUS = "get_workspace_status"
    LIST_WORKSPACES = "list_workspaces"
    READ_FILE_SUMMARY = "read_file_summary"
    COMMIT_CHECKPOINT = "commit_checkpoint"
    LIST_PENDING_CHECKPOINT_PUBLICATIONS = "list_pending_checkpoint_publications"
    COMPLETE_CHECKPOINT_PUBLICATION = "complete_checkpoint_publication"
    UNMOUNT_WORKSPACE = "unmount_workspace"
    CLOSE_WORKSPACE = "close_workspace"
    DESTROY_EPHEMERAL_WORKSPACE = "destroy_ephemeral_workspace"
    SHUTDOWN = "shutdown"


class IdempotencyScope(StrEnum):
    NONE = "none"
    DURABLE = "durable"
    PROCESS_LOCAL = "process_local"


@dataclass(frozen=True, slots=True)
class OperationMetadata:
    mutates: bool
    idempotency_scope: IdempotencyScope

    def __post_init__(self) -> None:
        if self.mutates != (self.idempotency_scope is not IdempotencyScope.NONE):
            raise ValueError("mutation flag and idempotency scope must agree")


_READ_ONLY = OperationMetadata(
    mutates=False,
    idempotency_scope=IdempotencyScope.NONE,
)
_DURABLE_MUTATION = OperationMetadata(
    mutates=True,
    idempotency_scope=IdempotencyScope.DURABLE,
)
_PROCESS_LOCAL_MUTATION = OperationMetadata(
    mutates=True,
    idempotency_scope=IdempotencyScope.PROCESS_LOCAL,
)


OPERATION_METADATA: Final[dict[WorkspaceOperation, OperationMetadata]] = {
    WorkspaceOperation.HELLO: _READ_ONLY,
    WorkspaceOperation.HEALTH: _READ_ONLY,
    WorkspaceOperation.CREATE_WORKSPACE: _DURABLE_MUTATION,
    WorkspaceOperation.APPLY_POLICY: _DURABLE_MUTATION,
    WorkspaceOperation.MOUNT_WORKSPACE: _PROCESS_LOCAL_MUTATION,
    WorkspaceOperation.PREFETCH: _PROCESS_LOCAL_MUTATION,
    WorkspaceOperation.GET_CHANGE_JOURNAL: _READ_ONLY,
    WorkspaceOperation.GET_WORKSPACE_STATUS: _READ_ONLY,
    WorkspaceOperation.LIST_WORKSPACES: _READ_ONLY,
    WorkspaceOperation.READ_FILE_SUMMARY: _READ_ONLY,
    WorkspaceOperation.COMMIT_CHECKPOINT: _DURABLE_MUTATION,
    WorkspaceOperation.LIST_PENDING_CHECKPOINT_PUBLICATIONS: _READ_ONLY,
    WorkspaceOperation.COMPLETE_CHECKPOINT_PUBLICATION: _DURABLE_MUTATION,
    WorkspaceOperation.UNMOUNT_WORKSPACE: _PROCESS_LOCAL_MUTATION,
    WorkspaceOperation.CLOSE_WORKSPACE: _DURABLE_MUTATION,
    WorkspaceOperation.DESTROY_EPHEMERAL_WORKSPACE: _DURABLE_MUTATION,
    WorkspaceOperation.SHUTDOWN: _PROCESS_LOCAL_MUTATION,
}


class WorkspaceProtocolError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    operation: str
    workspace_id: str | None = None
    message: str


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    ok: bool
    result: Any | None = None
    error: WorkspaceProtocolError | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> "WorkspaceResponse":
        if self.ok and self.error is not None:
            raise ValueError("successful workspace response cannot contain an error")
        if not self.ok and self.error is None:
            raise ValueError("failed workspace response must contain an error")
        return self


class AdvertisedOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: WorkspaceOperation
    mutates: bool
    idempotency_scope: IdempotencyScope


class WorkspaceHello(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str
    protocol_version: int
    max_frame_bytes: int
    capabilities: list[str]
    operations: list[AdvertisedOperation]
    build_fingerprint: str


class WorkspaceHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready"]
    mounted_workspaces: int


class WorkspacePolicyApplied(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    applied: Literal[True]


class WorkspacePrefetch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    files: int
    bytes: int


class WorkspaceFileSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    size: int
    preview: str


class WorkspaceUnmounted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    mounted: Literal[False]


class WorkspaceClosed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    state: Literal["closed"]


class WorkspaceDestroyed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    destroyed: Literal[True]


class WorkspaceShutdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shutdown: Literal[True]


class CheckpointPublicationCompleted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_id: str
    memory_id: str
    published: Literal[True]


def operation_metadata(operation: WorkspaceOperation | str) -> OperationMetadata:
    try:
        typed_operation = WorkspaceOperation(operation)
    except ValueError as error:
        raise ValueError(f"unsupported workspace operation: {operation}") from error
    return OPERATION_METADATA[typed_operation]


def request_payload(
    operation: WorkspaceOperation,
    request_id: str,
    *,
    idempotency_key: str | None,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "request_id": request_id,
        "operation": operation.value,
        **arguments,
    }
    if idempotency_key is not None:
        payload["idempotency_key"] = idempotency_key
    return payload
