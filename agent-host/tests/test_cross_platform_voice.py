import os
import sys
import unittest
from unittest.mock import patch

from reframe_agent_host.keyphrases.pocketsphinx_helpers import decoder_config


class CrossPlatformVoiceTests(unittest.TestCase):
    def test_pocketsphinx_decoder_logs_to_platform_null_device(self):
        with patch.dict(sys.modules, {"pocketsphinx": FakePocketSphinx}):
            config = decoder_config()

        self.assertEqual(config["logfn"], os.devnull)


class FakeConfig(dict):
    def set_string(self, key, value):
        self[key] = value


class FakePocketSphinx:
    Config = FakeConfig

    @staticmethod
    def get_model_path():
        return "/models"


if __name__ == "__main__":
    unittest.main()
