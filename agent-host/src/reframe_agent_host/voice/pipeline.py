from __future__ import annotations

import time
from threading import Event

from reframe_agent_host.agent_flow.machine_state import MachineStateProvider
from reframe_agent_host.agent_flow.memory_retrieval import MemoryRetrievalPlanner
from reframe_agent_host.agent_flow.task_execution import TaskExecutionPlanner
from reframe_agent_host.agent_flow.voice_turn_flow import BamlVoiceTurnFlow
from reframe_agent_host.speech.transcription import create_transcriber
from reframe_agent_host.speech.triggers import TriggerPhraseMatcher
from reframe_agent_host.speech.kokoro_onnx import KokoroOnnxSpeaker
from reframe_agent_host.speech.tts import QueuedTextSpeaker
from reframe_agent_host.voice.barge_in import TtsBargeInDetector
from reframe_agent_host.voice.conversation_mode import ConversationModeController
from reframe_agent_host.voice.turn_capture import VoiceTurnCapture
from reframe_agent_host.voice.turn_capture import CaptureStreamEventHandler
from reframe_agent_host.voice.turn_processor import VoiceTurnProcessor
from reframe_agent_host.voice.types import (
    CaptureResult,
    VoicePipelineConfig,
    VoicePipelineEventHandler,
    VoiceTurnControl,
    VoiceTurnResult,
)


class VoiceTurnPipeline:
    def __init__(self, config: VoicePipelineConfig) -> None:
        self._config = config
        self._conversation_mode = ConversationModeController(config.conversation_mode)
        self._transcriber = create_transcriber(config.transcription)
        self._trigger_matcher = TriggerPhraseMatcher(config.triggers)
        self._speaker = QueuedTextSpeaker(KokoroOnnxSpeaker())
        self._barge_in_detector = TtsBargeInDetector(config.voice_activity)
        self._machine_state = MachineStateProvider()
        self._prepared = False

    async def run_once(
        self,
        on_event: VoicePipelineEventHandler | None = None,
    ) -> VoiceTurnResult:
        total_started_at = time.perf_counter()
        model_prepare_seconds = self.prepare(on_event)
        capture = self.capture_once(on_event)
        return await self.process_capture(
            capture,
            model_prepare_seconds,
            total_started_at,
            on_event,
        )

    def prepare(
        self,
        on_event: VoicePipelineEventHandler | None,
    ) -> float:
        if self._prepared:
            return 0.0

        self._emit(on_event, "preparing", "loading local speech models")
        prepare_started_at = time.perf_counter()
        self._emit(on_event, "machine-state", "loading IP geolocation")
        self._machine_state.start()
        self._transcriber.prepare()
        self._speaker.prepare()
        self._machine_state.wait_until_ready()
        model_prepare_seconds = time.perf_counter() - prepare_started_at
        self._prepared = True
        self._emit(on_event, "machine-state", "loaded IP geolocation")
        self._emit(
            on_event,
            "ready",
            f"local speech models loaded in {model_prepare_seconds:.3f}s",
        )
        return model_prepare_seconds

    def capture_once(
        self,
        on_event: VoicePipelineEventHandler | None,
        stop_event: Event | None = None,
    ) -> CaptureResult:
        capture = VoiceTurnCapture(
            self._config,
            self._conversation_mode.get(),
            mode_controller=self._conversation_mode,
            audio_frame_handler=self._handle_tts_barge_in_frame,
        ).capture(on_event, stop_event=stop_event)
        self._conversation_mode.set(capture.conversation_mode)
        return capture

    def capture_speculative_once(
        self,
        on_event: VoicePipelineEventHandler | None,
        on_capture_event: CaptureStreamEventHandler,
        stop_event: Event | None = None,
    ) -> None:
        VoiceTurnCapture(
            self._config,
            self._conversation_mode.get(),
            mode_controller=self._conversation_mode,
            audio_frame_handler=self._handle_tts_barge_in_frame,
        ).capture_speculative_once(
            on_event,
            on_capture_event,
            stop_event=stop_event,
        )

    def capture_speculative_session(
        self,
        on_event: VoicePipelineEventHandler | None,
        on_capture_event: CaptureStreamEventHandler,
        stop_event: Event | None = None,
        max_turns: int = 0,
    ) -> None:
        VoiceTurnCapture(
            self._config,
            self._conversation_mode.get(),
            mode_controller=self._conversation_mode,
            audio_frame_handler=self._handle_tts_barge_in_frame,
        ).capture_speculative_session(
            on_event,
            on_capture_event,
            stop_event=stop_event,
            max_turns=max_turns,
        )

    async def process_capture(
        self,
        capture: CaptureResult,
        model_prepare_seconds: float,
        total_started_at: float,
        on_event: VoicePipelineEventHandler | None,
        turn_control: VoiceTurnControl | None = None,
    ) -> VoiceTurnResult:
        processor = self._create_processor()
        try:
            return await processor.process(
                capture,
                capture.conversation_mode,
                model_prepare_seconds,
                total_started_at,
                on_event,
                turn_control=turn_control,
            )
        finally:
            await processor.close()

    def apply_capture_mode(self, capture: CaptureResult) -> None:
        self._conversation_mode.set(capture.conversation_mode)

    def _create_processor(self) -> VoiceTurnProcessor:
        return VoiceTurnProcessor(
            self._config,
            self._transcriber,
            self._trigger_matcher,
            MemoryRetrievalPlanner(session_id=self._config.session_id),
            TaskExecutionPlanner(),
            self._speaker,
            mode_controller=self._conversation_mode,
            turn_flow=BamlVoiceTurnFlow(
                session_id=self._config.session_id,
                conversation_id=self._config.conversation_id,
                machine_state_provider=self._machine_state,
            ),
        )

    def _emit(
        self,
        on_event: VoicePipelineEventHandler | None,
        stage: str,
        message: str,
    ) -> None:
        if on_event is not None:
            on_event(stage, message)

    def _handle_tts_barge_in_frame(
        self,
        frame,
        on_event: VoicePipelineEventHandler | None,
    ) -> None:
        if self._barge_in_detector.accept(
            frame,
            tts_active=self._speaker.is_speaking(),
        ):
            if self._speaker.interrupt("human voice"):
                self._emit(on_event, "barge-in", "human voice")
