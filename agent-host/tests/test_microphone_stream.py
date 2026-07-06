from unittest.mock import patch
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

    def test_enter_falls_back_to_next_resolved_device(self):
        sounddevice = FallbackSoundDevice(failing_device=1)
        microphone = MicrophoneStream(
            AudioInputConfig(
                start_retries=0,
                start_retry_delay_seconds=0,
            )
        )

        with (
            patch.dict("sys.modules", {"sounddevice": sounddevice}),
            patch(
                "reframe_agent_host.voice.microphone.resolve_input_devices",
                return_value=(1, 2),
            ),
            patch(
                "reframe_agent_host.voice.microphone.device_default_sample_rate",
                return_value=16_000,
            ),
            patch(
                "reframe_agent_host.voice.microphone.device_input_channels",
                return_value=1,
            ),
            patch(
                "reframe_agent_host.voice.microphone.device_summary",
                side_effect=lambda device: f"device {device}",
            ),
        ):
            with microphone:
                self.assertEqual(microphone.device_summary, "device 2")

        self.assertEqual([stream.device for stream in sounddevice.streams], [1, 2])
        self.assertTrue(sounddevice.streams[0].closed)
        self.assertTrue(sounddevice.streams[1].stopped)
        self.assertTrue(sounddevice.streams[1].closed)


class FallbackStream:
    def __init__(self, device, failing_device):
        self.device = device
        self._failing_device = failing_device
        self.closed = False
        self.stopped = False

    def start(self):
        if self.device == self._failing_device:
            raise RuntimeError("host API failed")

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


class FallbackSoundDevice:
    def __init__(self, failing_device):
        self._failing_device = failing_device
        self.streams = []

    def InputStream(self, **kwargs):
        stream = FallbackStream(kwargs["device"], self._failing_device)
        self.streams.append(stream)
        return stream


if __name__ == "__main__":
    unittest.main()
