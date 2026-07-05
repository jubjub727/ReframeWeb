import unittest

import numpy as np

from reframe_agent_host.voice.microphone import AudioInputConfig, MicrophoneStream


class FakeStream:
    def __init__(self, sounddevice):
        self._sounddevice = sounddevice
        self.closed = False

    def start(self):
        self._sounddevice.starts += 1
        if self._sounddevice.starts <= self._sounddevice.failures:
            raise RuntimeError("transient start failure")

    def close(self):
        self.closed = True


class FakeSoundDevice:
    def __init__(self, failures):
        self.failures = failures
        self.starts = 0
        self.streams = []

    def InputStream(self, **_kwargs):
        stream = FakeStream(self)
        self.streams.append(stream)
        return stream


class MicrophoneStreamTests(unittest.TestCase):
    def test_to_mono_auto_selects_strongest_channel(self):
        microphone = MicrophoneStream(AudioInputConfig(channel=-1))
        stereo = np.array(
            [
                [0.01, 0.2],
                [-0.01, -0.2],
                [0.01, 0.2],
            ],
            dtype=np.float32,
        )

        mono = microphone._to_mono(stereo)

        np.testing.assert_allclose(mono, stereo[:, 1])

    def test_to_mono_explicit_channel_still_selects_that_channel(self):
        microphone = MicrophoneStream(AudioInputConfig(channel=0))
        stereo = np.array(
            [
                [0.01, 0.2],
                [-0.01, -0.2],
                [0.01, 0.2],
            ],
            dtype=np.float32,
        )

        mono = microphone._to_mono(stereo)

        np.testing.assert_allclose(mono, stereo[:, 0])

    def test_open_started_stream_retries_transient_start_failure(self):
        sounddevice = FakeSoundDevice(failures=1)
        microphone = MicrophoneStream(
            AudioInputConfig(
                start_retries=2,
                start_retry_delay_seconds=0,
            )
        )

        stream = microphone._open_started_stream(sounddevice, {})

        self.assertIs(stream, sounddevice.streams[1])
        self.assertTrue(sounddevice.streams[0].closed)
        self.assertEqual(sounddevice.starts, 2)


if __name__ == "__main__":
    unittest.main()
