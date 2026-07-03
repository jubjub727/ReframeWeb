from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from reframe_memory.models import MemoryNode
from reframe_memory.search import StringSearch, TagSearch


@dataclass(frozen=True)
class TimestampBreadth:
    created_after: datetime
    updated_after: datetime
    read_after: datetime

    @classmethod
    def build(
        cls,
        *,
        created_after: str,
        updated_after: str,
        read_after: str,
    ) -> "TimestampBreadth":
        return cls(
            created_after=_parse_timestamp(created_after),
            updated_after=_parse_timestamp(updated_after),
            read_after=_parse_timestamp(read_after),
        )

    def matches(self, node: MemoryNode[Any]) -> bool:
        timestamps = node.timestamps
        if _aware(timestamps.created_at) < self.created_after:
            return False
        if _aware(timestamps.updated_at) < self.updated_after:
            return False
        if timestamps.read_at is None:
            return True
        return _aware(timestamps.read_at) >= self.read_after


@dataclass(frozen=True)
class GraphSearchHints:
    tags: TagSearch = TagSearch()
    strings: StringSearch = StringSearch()

    def matches(self, node: MemoryNode[Any], fields: Sequence[str]) -> bool:
        if self._excluded_by_tags(node):
            return False

        has_positive = self._has_positive_terms()
        if not has_positive:
            return False

        return self._matches_positive_tag(node) or self._matches_positive_string(
            node,
            fields,
        )

    def _excluded_by_tags(self, node: MemoryNode[Any]) -> bool:
        excluded = set(self.tags.none_of)
        return bool(excluded and excluded.intersection(node.tags))

    def _has_positive_terms(self) -> bool:
        return bool(
            self.tags.any_of
            or self.tags.all_of
            or self.strings.contains
            or self.strings.equals
        )

    def _matches_positive_tag(self, node: MemoryNode[Any]) -> bool:
        positive_tags = set(self.tags.any_of).union(self.tags.all_of)
        return bool(positive_tags and positive_tags.intersection(node.tags))

    def _matches_positive_string(
        self,
        node: MemoryNode[Any],
        fields: Sequence[str],
    ) -> bool:
        values = _field_values(node.content, fields)
        lowered_values = tuple(value.lower() for value in values)

        for term in self.strings.contains:
            lowered_term = term.lower()
            if any(lowered_term in value for value in lowered_values):
                return True

        return any(value in self.strings.equals for value in values)


def candidate_matches(
    node: MemoryNode[Any],
    *,
    fields: Sequence[str],
    hints: GraphSearchHints,
    breadth: TimestampBreadth,
) -> bool:
    return breadth.matches(node) and hints.matches(node, fields)


def _field_values(content: object, fields: Sequence[str]) -> tuple[str, ...]:
    values: list[str] = []
    for field in fields:
        value = getattr(content, field, None)
        if value is not None:
            values.append(str(value))
    return tuple(values)


def _parse_timestamp(value: str) -> datetime:
    stamp = value.strip()
    if not stamp:
        raise ValueError("timestamp breadth values cannot be empty")
    return _aware(datetime.fromisoformat(stamp.replace("Z", "+00:00")))


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
