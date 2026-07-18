from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class WorkspaceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MemorySource(WorkspaceModel):
    memory_id: str
    source_kind: Literal["directory", "checkpoint"]
    source_path: str | None = None
    backing_store: str | None = None
    manifest_id: str | None = None

    @model_validator(mode="after")
    def validate_locator(self) -> "MemorySource":
        if self.source_kind == "directory":
            if self.source_path is None or self.backing_store or self.manifest_id:
                raise ValueError("directory memory source requires only source_path")
        elif self.source_path or self.backing_store is None or self.manifest_id is None:
            raise ValueError(
                "checkpoint memory source requires backing_store and manifest_id"
            )
        return self


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
    state: str
    worktree: str
    head_manifest: str | None
    memory_ids: list[str]
    changes: list[WorkspaceChange]


class WorkspaceSummary(WorkspaceModel):
    session_id: str
    name: str
    state: str
    head_manifest: str | None
    memory_ids: list[str]
    created_at: int
    updated_at: int


class CheckpointResult(WorkspaceModel):
    session_id: str
    manifest_id: str
    retained_paths: list[str]
    remaining_changes: list[WorkspaceChange]
    memory_id: str | None = None


class MountedWorkspace(WorkspaceModel):
    session_id: str
    mount_path: str
    resident_files: int
    resident_bytes: int


class ResolvedWorkspacePlan(WorkspaceModel):
    memory_sources: list[MemorySource]
    prefetch_paths: list[str]
    scratch_paths: list[str]
