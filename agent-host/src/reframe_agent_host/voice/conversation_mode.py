from __future__ import annotations

from threading import Lock

from baml_sdk import turn_context as baml_turn_context


class ConversationModeController:
    def __init__(self, mode: baml_turn_context.ConversationMode) -> None:
        self._mode = mode
        self._version = 0
        self._lock = Lock()

    def get(self) -> baml_turn_context.ConversationMode:
        with self._lock:
            return self._mode

    def snapshot(self) -> tuple[baml_turn_context.ConversationMode, int]:
        with self._lock:
            return self._mode, self._version

    def set(self, mode: baml_turn_context.ConversationMode) -> bool:
        with self._lock:
            if self._mode == mode:
                return False
            self._mode = mode
            self._version += 1
            return True

    def turn_off_conversation(self) -> bool:
        return self.set(baml_turn_context.ConversationMode.WAKE_COMMAND)
