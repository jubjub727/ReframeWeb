from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from baml_sdk import context as baml_context
from reframe_agent_host.keyphrases import KeyphraseDetection
from reframe_agent_host.voice.activity import DetectedUtterance


CaptureStreamEventKind = Literal["endpoint", "resumed", "confirmed", "mode_switch"]


@dataclass(frozen=True)
class CaptureResult:
    conversation_mode: baml_context.ConversationMode
    keyphrase_detection: KeyphraseDetection | None
    utterance: DetectedUtterance | None
    mode_switched: bool
    keyphrase_wait_seconds: float | None
    listen_seconds: float
    wait_for_speech_seconds: float | None
    speech_capture_wall_seconds: float | None


@dataclass(frozen=True)
class CaptureStreamEvent:
    kind: CaptureStreamEventKind
    turn_id: int
    capture: CaptureResult | None = None


class VoiceTurnControl:
    def __init__(self) -> None:
        self._cancelled = asyncio.Event()
        self._committed = asyncio.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def commit(self) -> None:
        self._committed.set()

    async def checkpoint(self) -> None:
        if self._cancelled.is_set():
            raise asyncio.CancelledError

    async def wait_for_commit_or_cancel(self, timeout_seconds: float) -> bool:
        if self._committed.is_set():
            await self.checkpoint()
            return True
        return await self._wait(timeout_seconds)

    async def wait_until_committed(self) -> None:
        if self._committed.is_set():
            await self.checkpoint()
            return
        await self._wait(None)

    async def _wait(self, timeout_seconds: float | None) -> bool:
        commit_task = asyncio.create_task(self._committed.wait())
        cancel_task = asyncio.create_task(self._cancelled.wait())
        try:
            done, pending = await asyncio.wait(
                {commit_task, cancel_task},
                timeout=(
                    None if timeout_seconds is None else max(0.0, timeout_seconds)
                ),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if cancel_task in done:
                raise asyncio.CancelledError
            if commit_task in done:
                await self.checkpoint()
                return True
            await self.checkpoint()
            return False
        finally:
            for task in (commit_task, cancel_task):
                if not task.done():
                    task.cancel()
