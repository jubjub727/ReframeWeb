from __future__ import annotations

from datetime import datetime, timezone

from reframe_memory import MemoryNode, MemoryTimestamps, Provider


class FakeModel:
    def __init__(self, **values):
        self.__dict__.update(values)

    def model_dump(self, mode="json"):
        return dict(self.__dict__)


def provider(provider_id: str, surface: str):
    now = datetime.now(timezone.utc)
    return MemoryNode(
        id=provider_id,
        tags=(),
        timestamps=MemoryTimestamps(
            created_at=now,
            updated_at=now,
            read_at=None,
        ),
        content=Provider(
            name=provider_id,
            description="Test provider",
            baml_surface=surface,
        ),
    )
