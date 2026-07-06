from contextlib import nullcontext
import unittest
from unittest.mock import patch

import numpy as np

from reframe_agent_host.speech import tts
from reframe_agent_host.speech.chunking import speech_chunks
from reframe_agent_host.speech.tts import KokoroSpeaker


class SpeechChunkTests(unittest.TestCase):
    def test_short_text_stays_single_chunk(self):
        self.assertEqual(speech_chunks("  Hello   there.  "), ("Hello there.",))

    def test_long_text_splits_before_kokoro_inference(self):
        text = (
            "This is a deliberately long spoken response without much punctuation "
            "so the text to speech system can begin generating audio from a small "
            "first chunk instead of waiting for the entire paragraph to synthesize."
        )

        chunks = speech_chunks(text, max_chars=64, first_chunk_chars=64)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 64 for chunk in chunks))
        self.assertEqual(" ".join(chunks), text)

    def test_joke_first_chunk_is_full_setup_sentence(self):
        chunks = speech_chunks(
            "A man walks into a library and asks for books about paranoia. "
            "The librarian whispers, 'They're right behind you.'"
        )

        self.assertEqual(
            chunks[0],
            "A man walks into a library and asks for books about paranoia.",
        )
        self.assertGreater(len(chunks[0]), 42)


class KokoroSpeakerPlaybackTests(unittest.TestCase):
    def test_next_chunk_synthesizes_after_first_chunk_is_queued(self):
        sounddevice = FakeSoundDevice()
        output = FakeOutput()
        pipeline = FakePipeline(output)
        speaker = KokoroSpeaker()
        speaker._pipeline = pipeline
        speaker._output = output

        with (
            patch.object(tts, "_sounddevice", return_value=sounddevice),
            patch.object(tts, "_torch_inference_mode", return_value=nullcontext()),
        ):
            speaker.speak(
                (
                    "A man walks into a library and asks for books about paranoia. "
                    "The librarian whispers, They are right behind you."
                ),
                on_event=lambda _stage, _message: None,
            )

        self.assertGreaterEqual(len(pipeline.calls), 2)
        self.assertEqual(pipeline.calls[0].enqueue_count, 0)
        self.assertEqual(pipeline.calls[1].enqueue_count, 1)
        self.assertEqual(output.waits, 1)


class PipelineCall:
    def __init__(self, text, enqueue_count):
        self.text = text
        self.enqueue_count = enqueue_count


class FakePipeline:
    def __init__(self, output):
        self._output = output
        self.calls = []

    def __call__(self, text, **_kwargs):
        self.calls.append(
            PipelineCall(
                text=text,
                enqueue_count=self._output.enqueues,
            )
        )
        yield FakeResult()


class FakeResult:
    audio = None

    def __init__(self):
        self.audio = FakeAudio()


class FakeAudio:
    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return np.zeros(10, dtype=np.float32)


class FakeSoundDevice:
    def __init__(self):
        self.play_count = 0
        self.wait_count = 0

    def stop(self):
        return None

    def play(self, _samples, _sample_rate):
        self.play_count += 1

    def wait(self):
        self.wait_count += 1


class FakeOutput:
    def __init__(self):
        self.enqueues = 0
        self.waits = 0

    def start(self, _sounddevice):
        return None

    def clear(self):
        return None

    def enqueue(self, _samples):
        self.enqueues += 1
        return 10

    def wait_until_drained(self):
        self.waits += 1


if __name__ == "__main__":
    unittest.main()
