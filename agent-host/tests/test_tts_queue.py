from threading import Event, Lock
import time
import unittest

from reframe_agent_host.speech.tts import QueuedTextSpeaker


class QueuedTextSpeakerTests(unittest.TestCase):
    def test_speaks_replies_in_order_without_interrupting_active_reply(self):
        inner = BlockingSpeaker()
        speaker = QueuedTextSpeaker(inner, inter_reply_delay_seconds=0.01)

        speaker.speak("first")
        self.assertTrue(inner.started("first").wait(timeout=1))

        speaker.speak("second")
        time.sleep(0.05)
        self.assertFalse(inner.started("second").is_set())
        self.assertEqual(inner.interrupts, [])

        inner.release("first")
        self.assertTrue(inner.started("second").wait(timeout=1))
        inner.release("second")
        self.assertTrue(inner.finished("second").wait(timeout=1))

        self.assertEqual(
            inner.calls,
            [
                ("start", "first"),
                ("finish", "first"),
                ("start", "second"),
                ("finish", "second"),
            ],
        )

    def test_interrupt_clears_pending_replies(self):
        inner = BlockingSpeaker()
        speaker = QueuedTextSpeaker(inner, inter_reply_delay_seconds=0.01)

        speaker.speak("first")
        self.assertTrue(inner.started("first").wait(timeout=1))
        speaker.speak("second")

        self.assertTrue(speaker.interrupt("human voice"))
        self.assertTrue(inner.finished("first").wait(timeout=1))
        time.sleep(0.05)

        self.assertEqual(inner.interrupts, ["human voice"])
        self.assertFalse(inner.started("second").is_set())


class BlockingSpeaker:
    def __init__(self):
        self.calls = []
        self.interrupts = []
        self._lock = Lock()
        self._current: str | None = None
        self._started: dict[str, Event] = {}
        self._finished: dict[str, Event] = {}
        self._released: dict[str, Event] = {}

    def prepare(self):
        return None

    def interrupt(self, reason="human voice"):
        self.interrupts.append(reason)
        with self._lock:
            current = self._current
        if current is None:
            return False
        self.release(current)
        return True

    def is_speaking(self):
        with self._lock:
            return self._current is not None

    def speak(self, text, *, on_event=None):
        with self._lock:
            self._current = text
            self.calls.append(("start", text))
            started = self._started.setdefault(text, Event())
            released = self._released.setdefault(text, Event())
        started.set()
        released.wait(timeout=2)
        with self._lock:
            self.calls.append(("finish", text))
            if self._current == text:
                self._current = None
            finished = self._finished.setdefault(text, Event())
        finished.set()

    def started(self, text):
        with self._lock:
            return self._started.setdefault(text, Event())

    def finished(self, text):
        with self._lock:
            return self._finished.setdefault(text, Event())

    def release(self, text):
        self._released_event(text).set()

    def _released_event(self, text):
        with self._lock:
            return self._released.setdefault(text, Event())


if __name__ == "__main__":
    unittest.main()
