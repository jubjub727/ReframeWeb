from __future__ import annotations

from dataclasses import dataclass
import os


DEFAULT_MEMORY_URL = "surrealkv://.reframe-memory"
DEFAULT_MEMORY_NAMESPACE = "reframe"
DEFAULT_MEMORY_DATABASE = "memory"


@dataclass(frozen=True)
class MemoryConfig:
    url: str = DEFAULT_MEMORY_URL
    namespace: str = DEFAULT_MEMORY_NAMESPACE
    database: str = DEFAULT_MEMORY_DATABASE

    @classmethod
    def from_env(cls) -> "MemoryConfig":
        return cls(
            url=os.getenv("REFRAME_MEMORY_URL", DEFAULT_MEMORY_URL),
            namespace=os.getenv("REFRAME_MEMORY_NAMESPACE", DEFAULT_MEMORY_NAMESPACE),
            database=os.getenv("REFRAME_MEMORY_DATABASE", DEFAULT_MEMORY_DATABASE),
        )
