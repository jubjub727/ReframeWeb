from __future__ import annotations

from threading import Lock

from reframe_agent_host.baml_client import types


class ConversationModeController:
    def __init__(self, mode: types.ConversationMode) -> None:
        self._mode = mode
        self._version = 0
        self._lock = Lock()

    def get(self) -> types.ConversationMode:
        with self._lock:
            return self._mode

    def snapshot(self) -> tuple[types.ConversationMode, int]:
        with self._lock:
            return self._mode, self._version

    def set(self, mode: types.ConversationMode) -> bool:
        with self._lock:
            if self._mode == mode:
                return False
            self._mode = mode
            self._version += 1
            return True

    def turn_off_conversation(self) -> bool:
        return self.set(types.ConversationMode.WakeCommand)
