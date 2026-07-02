from __future__ import annotations

import time

from reframe_agent_host.agent_flow.conversation_evaluation import (
    ConversationEvaluationPlanner,
)
from reframe_agent_host.agent_flow.task_choice import TaskChoicePlanner
from reframe_agent_host.speech.transcription import FasterWhisperTranscriber
from reframe_agent_host.speech.triggers import TriggerPhraseMatcher
from reframe_agent_host.voice.turn_capture import VoiceTurnCapture
from reframe_agent_host.voice.turn_processor import VoiceTurnProcessor
from reframe_agent_host.voice.types import (
    VoicePipelineConfig,
    VoicePipelineEventHandler,
    VoiceTurnResult,
)


class VoiceTurnPipeline:
    def __init__(self, config: VoicePipelineConfig) -> None:
        self._config = config
        self._conversation_mode = config.conversation_mode
        self._transcriber = FasterWhisperTranscriber(config.transcription)
        self._trigger_matcher = TriggerPhraseMatcher(config.triggers)
        self._planner = TaskChoicePlanner(session_id=config.session_id)
        self._conversation_evaluation = ConversationEvaluationPlanner(
            session_id=config.session_id,
        )
        self._processor = VoiceTurnProcessor(
            config,
            self._transcriber,
            self._trigger_matcher,
            self._planner,
            self._conversation_evaluation,
        )

    async def run_once(
        self,
        on_event: VoicePipelineEventHandler | None = None,
    ) -> VoiceTurnResult:
        total_started_at = time.perf_counter()
        model_prepare_seconds = self._prepare_transcriber(on_event)
        capture = VoiceTurnCapture(
            self._config,
            self._conversation_mode,
        ).capture(on_event)
        self._conversation_mode = capture.conversation_mode
        return await self._processor.process(
            capture,
            self._conversation_mode,
            model_prepare_seconds,
            total_started_at,
            on_event,
        )

    def _prepare_transcriber(
        self,
        on_event: VoicePipelineEventHandler | None,
    ) -> float:
        self._emit(on_event, "preparing", "loading faster-whisper CUDA model")
        prepare_started_at = time.perf_counter()
        self._transcriber.prepare()
        model_prepare_seconds = time.perf_counter() - prepare_started_at
        self._emit(
            on_event,
            "ready",
            f"faster-whisper CUDA model loaded in {model_prepare_seconds:.3f}s",
        )
        return model_prepare_seconds

    def _emit(
        self,
        on_event: VoicePipelineEventHandler | None,
        stage: str,
        message: str,
    ) -> None:
        if on_event is not None:
            on_event(stage, message)
