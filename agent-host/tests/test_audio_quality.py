import unittest
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from reframe_agent_host.commands.parser import build_parser
from reframe_agent_host.commands.audio_quality_test import (
    _audio_config as _quality_audio_config,
)
from reframe_agent_host.commands.voice_turn import _audio_config as _voice_audio_config
from reframe_agent_host.speech.transcription import (
    DEFAULT_WHISPER_BEAM_SIZE,
    DEFAULT_WHISPER_INITIAL_PROMPT,
    DEFAULT_WHISPER_MODEL,
    WhisperTranscriberConfig,
)
from reframe_agent_host.voice.audio_calibration import recommend_input_gain
from reframe_agent_host.voice.audio_quality import analyze_audio_quality
from reframe_agent_host.voice.input_level import normalize_active_level
from reframe_agent_host.voice.resampling import AudioFrameProcessor


class AudioQualityTests(unittest.TestCase):
    def test_loud_speech_like_sample_passes(self):
        samples = _tone(0.2)

        report = analyze_audio_quality(samples, 16_000)

        self.assertTrue(report.ok)
        self.assertEqual(report.problems, ())

    def test_quiet_sample_fails(self):
        samples = _tone(0.02)

        report = analyze_audio_quality(samples, 16_000)

        self.assertFalse(report.ok)
        self.assertIn("speech is too quiet", report.problems)
        self.assertIn("active speech level is too low", report.problems)

    def test_clipped_sample_fails(self):
        samples = np.ones(16_000, dtype=np.float32)

        report = analyze_audio_quality(samples, 16_000)

        self.assertFalse(report.ok)
        self.assertIn("audio is clipping", report.problems)

    def test_quiet_yeti_like_sample_recommends_recording_gain(self):
        report = analyze_audio_quality(_tone(0.03), 16_000)

        gain = recommend_input_gain(report)

        self.assertGreaterEqual(gain, 4.0)
        self.assertLessEqual(gain, 8.0)

    def test_frame_processor_applies_gain_and_limits_peaks(self):
        processor = AudioFrameProcessor(
            source_rate=16_000,
            target_rate=16_000,
            chunk_samples=4,
            gain=4.0,
            limiter_ceiling=0.8,
        )

        chunks = processor.accept(np.array([0.1, -0.1, 0.5, -0.5], dtype=np.float32))

        self.assertEqual(len(chunks), 1)
        self.assertAlmostEqual(float(np.max(np.abs(chunks[0]))), 0.8, places=6)

    def test_parser_accepts_audio_quality_test(self):
        parser = build_parser()

        args = parser.parse_args(
            [
                "audio-quality-test",
                "--device",
                "Yeti",
                "--input-channel",
                "1",
                "--seconds",
                "2",
                "--save-calibration",
                "--no-prompt",
            ]
        )

        self.assertEqual(args.command, "audio-quality-test")
        self.assertEqual(args.device, "Yeti")
        self.assertEqual(args.input_channel, 1)
        self.assertEqual(args.seconds, 2)
        self.assertTrue(args.save_calibration)
        self.assertTrue(args.no_prompt)

    def test_voice_turn_defaults_to_large_v3_whisper(self):
        args = build_parser().parse_args(["voice-turn"])

        self.assertEqual(args.whisper_model, DEFAULT_WHISPER_MODEL)
        self.assertEqual(args.whisper_model, "large-v3")
        self.assertEqual(args.beam_size, DEFAULT_WHISPER_BEAM_SIZE)
        self.assertEqual(args.whisper_initial_prompt, DEFAULT_WHISPER_INITIAL_PROMPT)
        self.assertFalse(args.no_transcription_normalization)

    def test_whisper_config_normalizes_transcription_audio_by_default(self):
        config = WhisperTranscriberConfig()

        self.assertTrue(config.normalize_audio)
        self.assertEqual(config.beam_size, DEFAULT_WHISPER_BEAM_SIZE)
        self.assertEqual(config.initial_prompt, DEFAULT_WHISPER_INITIAL_PROMPT)

    def test_transcription_normalizer_lifts_quiet_active_audio(self):
        quiet = _tone(0.02)

        normalized = normalize_active_level(
            quiet,
            sample_rate=16_000,
            target_active_rms=0.12,
            max_gain=6.0,
            limiter_ceiling=0.95,
        )

        self.assertGreater(float(np.max(np.abs(normalized))), float(np.max(np.abs(quiet))))

    def test_transcription_normalizer_limits_loud_audio(self):
        loud = _tone(0.9)

        normalized = normalize_active_level(
            loud,
            sample_rate=16_000,
            target_active_rms=0.12,
            max_gain=6.0,
            limiter_ceiling=0.5,
        )

        self.assertLessEqual(float(np.max(np.abs(normalized))), 0.5)

    def test_audio_quality_test_can_use_saved_calibration(self):
        with TemporaryDirectory() as directory:
            calibration_path = Path(directory) / "calibration.json"
            calibration_path.write_text('{"input_gain": 3.75}', encoding="utf-8")
            args = Namespace(
                sample_rate=16_000,
                input_sample_rate=0,
                input_gain=1.0,
                limiter_ceiling=0.95,
                chunk_ms=32,
                input_channels=0,
                input_channel=0,
                device=None,
                use_calibration=True,
                calibration_file=str(calibration_path),
            )

            config = _quality_audio_config(args)

        self.assertEqual(config.input_gain, 3.75)

    def test_voice_audio_config_uses_saved_calibration(self):
        with TemporaryDirectory() as directory:
            calibration_path = Path(directory) / "calibration.json"
            calibration_path.write_text('{"input_gain": 4.25}', encoding="utf-8")
            args = _voice_args(
                input_gain=None,
                audio_calibration_file=str(calibration_path),
            )

            config = _voice_audio_config(args)

        self.assertEqual(config.input_gain, 4.25)

    def test_voice_audio_config_explicit_gain_overrides_calibration(self):
        with TemporaryDirectory() as directory:
            calibration_path = Path(directory) / "calibration.json"
            calibration_path.write_text('{"input_gain": 4.25}', encoding="utf-8")
            args = _voice_args(
                input_gain=2.0,
                audio_calibration_file=str(calibration_path),
            )

            config = _voice_audio_config(args)

        self.assertEqual(config.input_gain, 2.0)


def _tone(amplitude: float) -> np.ndarray:
    seconds = 1.0
    sample_rate = 16_000
    t = np.arange(int(sample_rate * seconds), dtype=np.float32) / sample_rate
    return (np.sin(2 * np.pi * 220 * t) * amplitude).astype(np.float32)


def _voice_args(**overrides):
    values = {
        "sample_rate": 16_000,
        "input_sample_rate": 0,
        "input_gain": None,
        "limiter_ceiling": 0.95,
        "chunk_ms": 32,
        "input_channels": 0,
        "input_channel": -1,
        "device": None,
        "ignore_audio_calibration": False,
        "audio_calibration_file": ".reframe-audio-calibration.json",
    }
    values.update(overrides)
    return Namespace(**values)


if __name__ == "__main__":
    unittest.main()
