import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reframe_agent_host.commands.parser import build_parser
from reframe_agent_host.commands.voice_config import transcription_config
from reframe_agent_host.speech.transcription import WhisperTranscriberConfig
from reframe_agent_host.speech.whisper_cpp_transcriber import (
    WhisperCppTranscriber,
    transcript_from_whisper_cpp_json,
)
from reframe_agent_host.speech.whisper_runtime import (
    resolve_whisper_cpp_binary,
    resolve_whisper_cpp_model,
    validate_transcription_runtime,
)


class TranscriptionRuntimeTests(unittest.TestCase):
    def test_voice_turn_parser_accepts_whisper_cpp_backend(self):
        args = build_parser().parse_args(
            [
                "voice-turn",
                "--transcriber",
                "whisper-cpp",
                "--transcriber-device",
                "metal",
                "--whisper-cpp-bin",
                "/opt/whisper/whisper-cli",
                "--whisper-cpp-model",
                "/models/ggml-large-v3.bin",
                "--whisper-cpp-extra-arg=--no-gpu",
                "--no-task-choice",
            ]
        )

        config = transcription_config(args)

        self.assertEqual(config.backend, "whisper-cpp")
        self.assertEqual(config.device, "metal")
        self.assertEqual(config.whisper_cpp_bin, "/opt/whisper/whisper-cli")
        self.assertEqual(config.whisper_cpp_model, "/models/ggml-large-v3.bin")
        self.assertEqual(config.whisper_cpp_extra_args, ("--no-gpu",))

    def test_transcription_check_parser_accepts_non_cuda_gpu(self):
        args = build_parser().parse_args(
            [
                "transcription-check",
                "--transcriber",
                "whisper-cpp",
                "--transcriber-device",
                "vulkan",
                "--whisper-cpp-model",
                "/models/ggml-base.bin",
            ]
        )

        self.assertEqual(args.command, "transcription-check")
        self.assertEqual(args.transcriber, "whisper-cpp")
        self.assertEqual(args.transcriber_device, "vulkan")

    def test_non_cuda_device_uses_whisper_cpp_runtime(self):
        config = WhisperTranscriberConfig(
            device="metal",
            whisper_cpp_bin="/opt/whisper/whisper-cli",
            whisper_cpp_model="/models/ggml-large-v3.bin",
        )

        with (
            patch(
                "reframe_agent_host.speech.whisper_runtime.resolve_whisper_cpp_binary",
                return_value=Path("/opt/whisper/whisper-cli"),
            ),
            patch(
                "reframe_agent_host.speech.whisper_runtime.resolve_whisper_cpp_model",
                return_value=Path("/models/ggml-large-v3.bin"),
            ),
        ):
            status = validate_transcription_runtime(config)

        self.assertEqual(status.backend, "whisper-cpp")
        self.assertEqual(status.device, "metal")

    def test_whisper_cpp_paths_resolve_to_absolute_paths(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            temp_dir = Path(directory)
            binary = temp_dir / "whisper-cli"
            model = temp_dir / "ggml-model.bin"
            binary.write_text("", encoding="utf-8")
            model.write_text("", encoding="utf-8")

            relative_binary = str(binary.relative_to(Path.cwd()))
            relative_model = str(model.relative_to(Path.cwd()))
            config = WhisperTranscriberConfig(whisper_cpp_model=relative_model)

            self.assertEqual(resolve_whisper_cpp_binary(relative_binary), binary)
            self.assertEqual(resolve_whisper_cpp_model(config), model)

    def test_whisper_cpp_command_includes_openvino_and_extra_args(self):
        config = WhisperTranscriberConfig(
            backend="whisper-cpp",
            device="openvino",
            whisper_cpp_extra_args=("--threads", "4"),
            language="en",
        )
        transcriber = WhisperCppTranscriber(config)
        transcriber._binary = Path("whisper-cli")
        transcriber._model = Path("ggml.bin")

        command = transcriber._command(Path("utterance.wav"), Path("transcript"))

        self.assertIn("--ov-e-device", command)
        self.assertIn("GPU", command)
        self.assertEqual(command[-2:], ["--threads", "4"])

    def test_whisper_cpp_transcribe_uses_configured_initial_prompt(self):
        samples = object()
        transcriber = WhisperCppTranscriber(
            WhisperTranscriberConfig(initial_prompt="Conversational context.")
        )

        with patch.object(transcriber, "transcribe_with_prompt") as transcribe:
            transcriber.transcribe(samples, 16_000)

        transcribe.assert_called_once_with(
            samples, 16_000, "Conversational context."
        )

    def test_whisper_cpp_json_transcript_uses_segments_and_language(self):
        transcript = transcript_from_whisper_cpp_json(
            {
                "result": {"language": "en"},
                "transcription": [
                    {"text": " hello", "offsets": {"from": 0, "to": 1500}},
                    {
                        "text": " world",
                        "timestamps": {
                            "from": "00:00:01,500",
                            "to": "00:00:02,000",
                        },
                    },
                ],
            },
            sample_rate=16_000,
            sample_count=32_000,
            fallback_language=None,
        )

        self.assertEqual(transcript.text, "hello world")
        self.assertEqual(transcript.language, "en")
        self.assertEqual(transcript.segments[0].start, 0.0)
        self.assertEqual(transcript.segments[0].end, 1.5)
        self.assertEqual(transcript.segments[1].start, 1.5)
        self.assertEqual(transcript.segments[1].end, 2.0)


if __name__ == "__main__":
    unittest.main()
