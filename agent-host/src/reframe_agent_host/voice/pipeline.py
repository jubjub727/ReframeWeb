from __future__ import annotations

import time
from threading import Event

from reframe_agent_host.agent_flow.conversation_evaluation import (
    ConversationEvaluationPlanner,
)
from reframe_agent_host.agent_flow.memory_retrieval import MemoryRetrievalPlanner
from reframe_agent_host.agent_flow.memory_relevance import MemoryRelevancePlanner
from reframe_agent_host.agent_flow.search_depth import SearchDepthPlanner
from reframe_agent_host.agent_flow.task_choice import TaskChoicePlanner
from reframe_agent_host.agent_flow.task_execution import TaskExecutionPlanner
from reframe_agent_host.agent_flow.task_prompt import TaskPromptPlanner
from reframe_agent_host.speech.transcription import create_transcriber
from reframe_agent_host.speech.triggers import TriggerPhraseMatcher
from reframe_agent_host.speech.kokoro_onnx import KokoroOnnxSpeaker
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
        self._speaker = KokoroOnnxSpeaker()
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
        self._transcriber.prepare()
        self._speaker.prepare()
        model_prepare_seconds = time.perf_counter() - prepare_started_at
        self._prepared = True
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
            TaskChoicePlanner(
                session_id=self._config.session_id,
                conversation_id=self._config.conversation_id,
            ),
            ConversationEvaluationPlanner(
                session_id=self._config.session_id,
                conversation_id=self._config.conversation_id,
            ),
            SearchDepthPlanner(
                session_id=self._config.session_id,
                conversation_id=self._config.conversation_id,
            ),
            MemoryRetrievalPlanner(session_id=self._config.session_id),
            MemoryRelevancePlanner(
                session_id=self._config.session_id,
                conversation_id=self._config.conversation_id,
            ),
            TaskPromptPlanner(
                session_id=self._config.session_id,
                conversation_id=self._config.conversation_id,
            ),
            TaskExecutionPlanner(),
            self._speaker,
            mode_controller=self._conversation_mode,
        )

    def _emit(
        self,
        on_event: VoicePipelineEventHandler | None,
        stage: str,
        message: str,
    ) -> None:
        if on_event is not None:
            on_event(stage, message)
