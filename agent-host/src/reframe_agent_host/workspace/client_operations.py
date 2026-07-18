from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

from reframe_agent_host.workspace.errors import WorkspaceError
from reframe_agent_host.workspace.models import (
    DaemonCheckpointResult,
    MemorySource,
    MountedWorkspace,
    PendingCheckpointPublication,
    WorkspaceChange,
    WorkspaceCreated,
    WorkspaceStatus,
    WorkspaceSummary,
)
from reframe_agent_host.workspace.protocol import (
    MAX_FRAME_BYTES,
    OPERATION_METADATA,
    PROTOCOL_VERSION,
    REQUIRED_CAPABILITIES,
    CheckpointPublicationCompleted,
    WorkspaceClosed,
    WorkspaceDestroyed,
    WorkspaceFileSummary,
    WorkspaceHealth,
    WorkspaceHello,
    WorkspaceOperation,
    WorkspacePolicyApplied,
    WorkspacePrefetch,
    WorkspaceShutdown,
    WorkspaceUnmounted,
)


_Model = TypeVar("_Model", bound=BaseModel)
_CHANGE_LIST = TypeAdapter(list[WorkspaceChange])
_SUMMARY_LIST = TypeAdapter(list[WorkspaceSummary])
_PENDING_PUBLICATION_LIST = TypeAdapter(list[PendingCheckpointPublication])


class TypedWorkspaceOperations:
    """Typed request/result adapters layered over the private raw request path."""

    def hello(self) -> WorkspaceHello:
        hello = self._validate_model(
            WorkspaceHello,
            self._request(WorkspaceOperation.HELLO),
            WorkspaceOperation.HELLO,
        )
        self._validate_hello(hello)
        return hello

    def health(self) -> WorkspaceHealth:
        return self._model_request(WorkspaceHealth, WorkspaceOperation.HEALTH)

    def create_workspace(
        self,
        *,
        name: str,
        session_id: str | None,
        memory_sources: Sequence[MemorySource],
        scratch_paths: Sequence[str],
    ) -> WorkspaceCreated:
        return self._model_request(
            WorkspaceCreated,
            WorkspaceOperation.CREATE_WORKSPACE,
            name=name,
            session_id=session_id,
            memory_sources=[source.model_dump(mode="json") for source in memory_sources],
            scratch_paths=list(scratch_paths),
        )

    def apply_policy(
        self,
        session_id: str,
        *,
        scratch_paths: Sequence[str],
    ) -> WorkspacePolicyApplied:
        return self._model_request(
            WorkspacePolicyApplied,
            WorkspaceOperation.APPLY_POLICY,
            session_id=session_id,
            scratch_paths=list(scratch_paths),
        )

    def mount_workspace(self, session_id: str) -> MountedWorkspace:
        return self._model_request(
            MountedWorkspace,
            WorkspaceOperation.MOUNT_WORKSPACE,
            session_id=session_id,
        )

    def prefetch(self, session_id: str, paths: Sequence[str]) -> WorkspacePrefetch:
        return self._model_request(
            WorkspacePrefetch,
            WorkspaceOperation.PREFETCH,
            session_id=session_id,
            paths=list(paths),
        )

    def get_change_journal(self, session_id: str) -> list[WorkspaceChange]:
        return self._validate_adapter(
            _CHANGE_LIST,
            self._request(
                WorkspaceOperation.GET_CHANGE_JOURNAL,
                session_id=session_id,
            ),
            WorkspaceOperation.GET_CHANGE_JOURNAL,
        )

    def get_workspace_status(self, session_id: str) -> WorkspaceStatus:
        return self._model_request(
            WorkspaceStatus,
            WorkspaceOperation.GET_WORKSPACE_STATUS,
            session_id=session_id,
        )

    def list_workspaces(self, *, active_only: bool = False) -> list[WorkspaceSummary]:
        return self._validate_adapter(
            _SUMMARY_LIST,
            self._request(
                WorkspaceOperation.LIST_WORKSPACES,
                active_only=active_only,
            ),
            WorkspaceOperation.LIST_WORKSPACES,
        )

    def read_file_summary(
        self,
        session_id: str,
        path: str,
        *,
        max_bytes: int | None = None,
    ) -> WorkspaceFileSummary:
        return self._model_request(
            WorkspaceFileSummary,
            WorkspaceOperation.READ_FILE_SUMMARY,
            session_id=session_id,
            path=path,
            max_bytes=max_bytes,
        )

    def commit_checkpoint(
        self,
        session_id: str,
        *,
        paths: Sequence[str],
        all: bool,
    ) -> DaemonCheckpointResult:
        return self._model_request(
            DaemonCheckpointResult,
            WorkspaceOperation.COMMIT_CHECKPOINT,
            session_id=session_id,
            paths=list(paths),
            all=all,
        )

    def list_pending_checkpoint_publications(
        self,
    ) -> list[PendingCheckpointPublication]:
        return self._validate_adapter(
            _PENDING_PUBLICATION_LIST,
            self._request(WorkspaceOperation.LIST_PENDING_CHECKPOINT_PUBLICATIONS),
            WorkspaceOperation.LIST_PENDING_CHECKPOINT_PUBLICATIONS,
        )

    def complete_checkpoint_publication(
        self,
        manifest_id: str,
        memory_id: str,
    ) -> CheckpointPublicationCompleted:
        return self._model_request(
            CheckpointPublicationCompleted,
            WorkspaceOperation.COMPLETE_CHECKPOINT_PUBLICATION,
            manifest_id=manifest_id,
            memory_id=memory_id,
        )

    def unmount_workspace(self, session_id: str) -> WorkspaceUnmounted:
        return self._model_request(
            WorkspaceUnmounted,
            WorkspaceOperation.UNMOUNT_WORKSPACE,
            session_id=session_id,
        )

    def close_workspace(self, session_id: str) -> WorkspaceClosed:
        return self._model_request(
            WorkspaceClosed,
            WorkspaceOperation.CLOSE_WORKSPACE,
            session_id=session_id,
        )

    def destroy_ephemeral_workspace(self, session_id: str) -> WorkspaceDestroyed:
        return self._model_request(
            WorkspaceDestroyed,
            WorkspaceOperation.DESTROY_EPHEMERAL_WORKSPACE,
            session_id=session_id,
        )

    def shutdown(self) -> WorkspaceShutdown:
        result = self._model_request(
            WorkspaceShutdown,
            WorkspaceOperation.SHUTDOWN,
        )
        self._after_shutdown()
        return result

    def _request(self, operation: WorkspaceOperation, **arguments: Any) -> Any:
        raise NotImplementedError

    def _after_shutdown(self) -> None:
        pass

    def _model_request(
        self,
        model: type[_Model],
        operation: WorkspaceOperation,
        **arguments: Any,
    ) -> _Model:
        return self._validate_model(
            model,
            self._request(operation, **arguments),
            operation,
        )

    @staticmethod
    def _validate_model(
        model: type[_Model],
        result: Any,
        operation: WorkspaceOperation,
    ) -> _Model:
        try:
            return model.model_validate(result)
        except ValidationError as error:
            raise WorkspaceError(
                f"workspace {operation.value} returned an invalid result"
            ) from error

    @staticmethod
    def _validate_adapter(
        adapter: TypeAdapter[Any],
        result: Any,
        operation: WorkspaceOperation,
    ) -> Any:
        try:
            return adapter.validate_python(result)
        except ValidationError as error:
            raise WorkspaceError(
                f"workspace {operation.value} returned an invalid result"
            ) from error

    @staticmethod
    def _validate_hello(hello: WorkspaceHello) -> None:
        if hello.service != "reframe-workspace-daemon" or not hello.build_fingerprint:
            raise WorkspaceError("workspace daemon identity is invalid")
        if hello.protocol_version != PROTOCOL_VERSION:
            raise WorkspaceError(
                "workspace daemon protocol version does not match the host"
            )
        if hello.max_frame_bytes != MAX_FRAME_BYTES:
            raise WorkspaceError("workspace daemon frame limit does not match the host")
        missing = REQUIRED_CAPABILITIES.difference(hello.capabilities)
        if missing:
            raise WorkspaceError(
                f"workspace daemon is missing capabilities: {', '.join(sorted(missing))}"
            )
        advertised = {
            item.name: (item.mutates, item.idempotency_scope)
            for item in hello.operations
        }
        expected = {
            operation: (metadata.mutates, metadata.idempotency_scope)
            for operation, metadata in OPERATION_METADATA.items()
        }
        if len(hello.operations) != len(expected) or advertised != expected:
            raise WorkspaceError("workspace daemon operation metadata does not match the host")
