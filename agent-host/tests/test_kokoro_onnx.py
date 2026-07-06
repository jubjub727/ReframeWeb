import tempfile
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


class FakeKokoro:
    def create(self, _text, **_kwargs):
        return np.zeros(16, dtype=np.float32), 24_000


class FakeOutput:
    def __init__(self):
        self.enqueues = 0

    def start(self, _sounddevice):
        return None

    def clear(self):
        return None

    def enqueue(self, _samples):
        self.enqueues += 1
        return 16

    def wait_until_drained(self):
        return None


class FakeSoundDevice:
    def stop(self):
        return None

    def play(self, _samples, _sample_rate):
        return None

    def wait(self):
        return None


if __name__ == "__main__":
    unittest.main()
