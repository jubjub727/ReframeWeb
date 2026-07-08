import tempfile
from threading import Event, Thread
import unittest
from unittest.mock import patch

import numpy as np

from reframe_agent_host.speech import kokoro_onnx
from reframe_agent_host.speech.kokoro_onnx import KokoroOnnxSpeaker


class KokoroOnnxAssetTests(unittest.TestCase):
    def test_downloads_missing_assets_to_configured_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            downloads = []

            def fake_download(url, path):
                downloads.append(url)
                path.write_bytes(b"asset")

            with (
                patch.dict("os.environ", {"REFRAME_KOKORO_ONNX_DIR": temp_dir}),
                patch.object(kokoro_onnx, "urlretrieve", fake_download),
            ):
                model_path, voices_path = kokoro_onnx.ensure_kokoro_onnx_assets()

            self.assertTrue(model_path.exists())
            self.assertTrue(voices_path.exists())
            self.assertEqual(downloads, [kokoro_onnx.MODEL_URL, kokoro_onnx.VOICES_URL])


class KokoroOnnxSpeakerTests(unittest.TestCase):
    def test_speaker_uses_onnx_backend_and_queues_audio(self):
        speaker = KokoroOnnxSpeaker()
        speaker._kokoro = FakeKokoro()
        speaker._output = FakeOutput()
        events = []

        with patch.object(kokoro_onnx, "_sounddevice", return_value=FakeSoundDevice()):
            speaker.speak(
                "A man walks into a library and asks for books about paranoia.",
                on_event=lambda stage, message: events.append((stage, message)),
            )

        self.assertEqual(speaker._output.enqueues, 1)
        self.assertTrue(any(event[0] == "tts-first-audio" for event in events))
        self.assertIn(("tts-started", "backend=kokoro-onnx chunks=1"), events)

    def test_interrupt_stops_active_playback_and_emits_event(self):
        speaker = KokoroOnnxSpeaker()
        speaker._kokoro = FakeKokoro(sample_count=2200)
        speaker._output = BlockingOutput()
        events = []

        with patch.object(kokoro_onnx, "_sounddevice", return_value=FakeSoundDevice()):
            thread = Thread(
                target=lambda: speaker.speak(
                    "alpha beta gamma delta",
                    on_event=lambda stage, message: events.append((stage, message)),
                )
            )
            thread.start()
            self.assertTrue(speaker._output.waiting.wait(timeout=1))
            speaker._output.played_samples_value = 2200
            with speaker._playback_lock:
                speaker._playback.playback_started_at = (
                    kokoro_onnx.time.perf_counter() - (1100 / 24_000)
                )

            self.assertTrue(speaker.interrupt("human voice"))

            thread.join(timeout=1)

        self.assertFalse(thread.is_alive())
        self.assertIn(
            ("tts-interrupted", "Last fully spoken word beta at character 10"),
            events,
        )
        self.assertFalse(any(event[0] == "tts-finished" for event in events))


class FakeKokoro:
    def __init__(self, sample_count=16):
        self.sample_count = sample_count

    def create(self, _text, **_kwargs):
        return np.zeros(self.sample_count, dtype=np.float32), 24_000


class FakeOutput:
    def __init__(self):
        self.enqueues = 0

    def start(self, _sounddevice):
        return None

    @property
    def played_samples(self):
        return 0

    def clear(self, *, reset_played_samples=False):
        return None

    def enqueue(self, _samples):
        self.enqueues += 1
        return len(_samples)

    def wait_until_drained(self):
        return None


class BlockingOutput(FakeOutput):
    def __init__(self):
        super().__init__()
        self.clear_count = 0
        self.interrupted = Event()
        self.waiting = Event()
        self.played_samples_value = 0

    @property
    def played_samples(self):
        return self.played_samples_value

    def clear(self, *, reset_played_samples=False):
        self.clear_count += 1
        if reset_played_samples:
            self.played_samples_value = 0
        if self.clear_count > 1:
            self.interrupted.set()

    def wait_until_drained(self):
        self.waiting.set()
        self.interrupted.wait(timeout=2)


class FakeSoundDevice:
    def stop(self):
        return None

    def play(self, _samples, _sample_rate):
        return None

    def wait(self):
        return None


if __name__ == "__main__":
    unittest.main()
