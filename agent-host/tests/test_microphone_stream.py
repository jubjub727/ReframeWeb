import unittest

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
