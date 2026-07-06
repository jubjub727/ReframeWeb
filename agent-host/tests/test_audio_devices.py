import unittest
from unittest.mock import patch

from reframe_agent_host.voice import audio_devices
from reframe_agent_host.voice.audio_devices import AudioDeviceInfo


class AudioDeviceResolutionTests(unittest.TestCase):
    def test_default_duplicate_tries_wdm_ks_last(self):
        devices = [
            _device(1, "Mic", "Windows WDM-KS", default=True),
            _device(2, "Mic", "MME"),
            _device(3, "Mic", "Windows DirectSound"),
        ]

        with patch.object(audio_devices, "list_input_devices", return_value=devices):
            self.assertEqual(
                audio_devices.resolve_input_devices(None),
                (3, 2, 1),
            )

    def test_missing_explicit_device_is_preserved(self):
        with patch.object(audio_devices, "list_input_devices", return_value=[]):
            self.assertEqual(audio_devices.resolve_input_devices(42), (42,))


def _device(
    index: int,
    name: str,
    host_api_name: str,
    *,
    default: bool = False,
) -> AudioDeviceInfo:
    return AudioDeviceInfo(
        index=index,
        name=name,
        host_api_name=host_api_name,
        max_input_channels=1,
        default_sample_rate=16_000,
        is_default_input=default,
    )


if __name__ == "__main__":
    unittest.main()
