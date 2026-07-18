from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DirectoryMemorySource(WorkspaceModel):
    memory_id: str
    source_kind: Literal["directory"] = "directory"
    source_path: str


class CheckpointMemorySource(WorkspaceModel):
    memory_id: str
    source_kind: Literal["checkpoint"] = "checkpoint"
    backing_store: str
    manifest_id: str


MemorySource: TypeAlias = Annotated[
    DirectoryMemorySource | CheckpointMemorySource,
    Field(discriminator="source_kind"),
]


class WorkspaceChange(WorkspaceModel):
    path: str
    kind: Literal["create", "write", "delete"]
    size: int | None


class WorkspaceCreated(WorkspaceModel):
    session_id: str
    worktree: str
    memory_ids: list[str]
    projected_files: int


class WorkspaceStatus(WorkspaceModel):
    session_id: str
    name: str
    state: Literal["active", "closed"]
    worktree: str
    head_manifest: str | None
    memory_ids: list[str]
    changes: list[WorkspaceChange]


class WorkspaceSummary(WorkspaceModel):
    session_id: str
    name: str
    state: Literal["active", "closed"]
    head_manifest: str | None
    memory_ids: list[str]
    created_at: int
    updated_at: int


class DaemonCheckpointResult(WorkspaceModel):
    session_id: str
    manifest_id: str
    retained_paths: list[str]
    remaining_changes: list[WorkspaceChange]


class PublishedCheckpointResult(DaemonCheckpointResult):
    memory_id: str


class PendingCheckpointPublication(WorkspaceModel):
    manifest_id: str
    session_id: str
    session_name: str
    base_memory_ids: list[str]
    retained_count: int


class MountedWorkspace(WorkspaceModel):
    session_id: str
    mount_path: str
    backend: Literal["fuse", "projfs", "winfsp"]
    resident_files: int
    resident_bytes: int


class ResolvedWorkspacePlan(WorkspaceModel):
    memory_sources: list[MemorySource]
    prefetch_paths: list[str]
    scratch_paths: list[str]
