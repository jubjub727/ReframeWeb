from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EquationCase:
    request: str
    reference: str
    alternatives: tuple[str, str, str]

    @property
    def candidates(self) -> tuple[str, str, str, str]:
        return (self.reference, *self.alternatives)
