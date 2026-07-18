from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from reframe_agent_host.workspace.errors import WorkspaceError
from reframe_agent_host.workspace.models import PendingCheckpointPublication

if TYPE_CHECKING:
    from reframe_agent_host.workspace.service import WorkspaceDaemon
    from reframe_memory import FilesystemMemoryNode, MemoryDatabase


DatabaseFactory = Callable[[], Awaitable["MemoryDatabase"]]
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CheckpointPublication:
    session_id: str
    session_name: str
    backing_store: str
    manifest_id: str
    base_memory_ids: tuple[str, ...]
    retained_count: int | None


class CheckpointPublisher:
    """Reconciles the daemon's transactional outbox into graph memory."""

    def __init__(
        self,
        daemon: WorkspaceDaemon,
        database_factory: DatabaseFactory,
    ) -> None:
        self._daemon = daemon
        self._database_factory = database_factory

    async def publish_manifest(self, manifest_id: str) -> FilesystemMemoryNode:
        publications = await self._pending_outbox()
        publication = next(
            (item for item in publications if item.manifest_id == manifest_id),
            None,
        )
        if publication is None:
            raise WorkspaceError(
                f"checkpoint publication outbox is missing manifest {manifest_id}"
            )
        return await self._publish_outbox(publication)

    async def publish_external(
        self,
        publication: CheckpointPublication,
    ) -> FilesystemMemoryNode:
        return await self._publish_graph(publication)

    async def reconcile(self, *, strict: bool = False) -> int:
        try:
            publications = await self._pending_outbox()
        except Exception as error:
            if strict:
                raise WorkspaceError(
                    f"read checkpoint publication outbox: {error}"
                ) from error
            _LOGGER.warning(
                "could not read the checkpoint publication outbox; "
                "pending publications will be retried: %s",
                error,
            )
            return 0
        published = 0
        for publication in publications:
            try:
                await self._publish_outbox(publication)
                published += 1
            except Exception as error:
                if strict:
                    raise WorkspaceError(
                        f"publish pending checkpoint {publication.manifest_id}: {error}"
                    ) from error
                _LOGGER.warning(
                    "could not publish pending checkpoint %s; "
                    "it remains queued for retry: %s",
                    publication.manifest_id,
                    error,
                )
        return published

    async def _publish_outbox(
        self,
        publication: PendingCheckpointPublication,
    ) -> FilesystemMemoryNode:
        checkpoint = CheckpointPublication(
            session_id=publication.session_id,
            session_name=publication.session_name,
            backing_store=str(self._daemon.store),
            manifest_id=publication.manifest_id,
            base_memory_ids=tuple(publication.base_memory_ids),
            retained_count=publication.retained_count,
        )
        node = await self._publish_graph(checkpoint)
        await asyncio.to_thread(
            self._daemon.complete_checkpoint_publication,
            publication.manifest_id,
            node.id,
        )
        return node

    async def _pending_outbox(self) -> list[PendingCheckpointPublication]:
        values = await asyncio.to_thread(
            self._daemon.list_pending_checkpoint_publications
        )
        return [
            value
            if isinstance(value, PendingCheckpointPublication)
            else PendingCheckpointPublication.model_validate(value)
            for value in values
        ]

    async def _publish_graph(
        self,
        publication: CheckpointPublication,
    ) -> FilesystemMemoryNode:
        from reframe_memory import CheckpointFilesystemMemory

        memory = CheckpointFilesystemMemory(
            title=f"{publication.session_name} checkpoint",
            description=_publication_description(publication.retained_count),
            backing_store=publication.backing_store,
            manifest_id=publication.manifest_id,
            base_memory_ids=publication.base_memory_ids,
        )
        async with self._database() as database:
            await database.apply_schema()
            await database.filesystem_memories.ensure_root()
            return await database.filesystem_memories.publish_checkpoint(
                memory,
                tags=("workspace", "checkpoint", "session-filesystem"),
            )

    @asynccontextmanager
    async def _database(self):
        database = await self._database_factory()
        try:
            yield database
        finally:
            await database.close()


def _publication_description(retained_count: int | None) -> str:
    count = (
        "selected files"
        if retained_count is None
        else f"{retained_count} retained files"
    )
    return f"Immutable session checkpoint containing {count}"
