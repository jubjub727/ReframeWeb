import unittest

import baml_sdk as types
from reframe_agent_host.commands.voice_loop import run_voice_turn_loop
from reframe_agent_host.voice.types import CaptureResult, CaptureStreamEvent


class FakePipeline:
    def __init__(self):
        self.capture_calls = 0
        self.processed = []
        self.applied_modes = []

    def prepare(self, _on_event):
        return 0.0

    def capture_speculative_session(
        self,
        _on_event,
        on_capture_event,
        _stop_event,
        max_turns,
    ):
        self.capture_calls += 1
        for turn_id in range(1, max_turns + 1):
            capture = _capture_result()
            on_capture_event(CaptureStreamEvent("endpoint", turn_id, capture))
            on_capture_event(CaptureStreamEvent("confirmed", turn_id, capture))

    async def process_capture(
        self,
        capture,
        _model_prepare_seconds,
        _total_started_at,
        _on_event,
        turn_control=None,
    ):
        if turn_control is not None:
            await turn_control.wait_until_committed()
        self.processed.append(capture)
        return f"result:{len(self.processed)}"

    def apply_capture_mode(self, capture):
        self.applied_modes.append(capture.conversation_mode)


class FailingThenRecoveringPipeline(FakePipeline):
    async def process_capture(
        self,
        capture,
        _model_prepare_seconds,
        _total_started_at,
        _on_event,
        turn_control=None,
    ):
        if turn_control is not None:
            await turn_control.wait_until_committed()
        self.processed.append(capture)
        if len(self.processed) == 1:
            raise RuntimeError("synthetic turn failure")
        return f"result:{len(self.processed)}"


class VoiceLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_loop_keeps_one_capture_session_across_turns(self):
        pipeline = FakePipeline()
        results = []
        handled = []

        await run_voice_turn_loop(
            turns=2,
            pipeline=pipeline,
            results=results,
            debug_output=False,
            event_handler_factory=lambda _started_at: lambda _stage, _message: None,
            result_handler=handled.append,
        )

        self.assertEqual(pipeline.capture_calls, 1)
        self.assertEqual(len(pipeline.processed), 2)
        self.assertEqual(results, ["result:1", "result:2"])
        self.assertEqual(handled, ["result:1", "result:2"])

    async def test_loop_reports_turn_error_and_keeps_listening(self):
        pipeline = FailingThenRecoveringPipeline()
        results = []
        handled = []
        events = []

        await run_voice_turn_loop(
            turns=2,
            pipeline=pipeline,
            results=results,
            debug_output=False,
            event_handler_factory=lambda _started_at: (
                lambda stage, message: events.append((stage, message))
            ),
            result_handler=handled.append,
        )

        self.assertEqual(len(pipeline.processed), 2)
        self.assertEqual(results, ["result:2"])
        self.assertEqual(handled, ["result:2"])
        self.assertIn(
            ("turn-error", "RuntimeError: synthetic turn failure"),
            events,
        )


def _capture_result():
    return CaptureResult(
        conversation_mode=types.ConversationMode.WAKE_COMMAND,
        keyphrase_detection=None,
        utterance=None,
        mode_switched=False,
        keyphrase_wait_seconds=0.0,
        listen_seconds=0.0,
        wait_for_speech_seconds=0.0,
        speech_capture_wall_seconds=0.0,
    )


if __name__ == "__main__":
    unittest.main()
