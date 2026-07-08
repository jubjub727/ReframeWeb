from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from reframe_agent_host.voice.microphone import AudioInputConfig
import baml_sdk as types
from reframe_agent_host.keyphrases import (
    KeyphraseDetection,
    KeyphraseSpotterConfig,
)
from reframe_agent_host.speech.transcription import Transcript, WhisperTranscriberConfig
from reframe_agent_host.speech.triggers import TriggerPhraseConfig, TriggerPhraseDetection
from reframe_agent_host.task_execution import PrimitiveDispatchResult
from reframe_agent_host.voice.activity import DetectedUtterance, VoiceActivityConfig
from reframe_memory import RetrievedMemoryContext


VoicePipelineEventHandler = Callable[[str, str], None]
CaptureStreamEventKind = Literal["endpoint", "resumed", "confirmed", "mode_switch"]


@dataclass(frozen=True)
class VoicePipelineConfig:
    audio: AudioInputConfig
    voice_activity: VoiceActivityConfig
    keyphrases: KeyphraseSpotterConfig
    triggers: TriggerPhraseConfig
    transcription: WhisperTranscriberConfig
    conversation_mode: types.ConversationMode
    task_choice_enabled: bool = True
    session_id: str | None = None
    conversation_id: str | None = None
    listen_timeout_seconds: float = 0.0
    post_activation_command_window_ms: int = 700
    debug_audio_dir: str | None = None
    debug_audio_seconds: float = 8.0
    debug_audio_period_seconds: float = 0.0


@dataclass(frozen=True)
class VoiceTurnTimings:
    model_prepare_seconds: float
    keyphrase_wait_seconds: float | None
    listen_seconds: float
    wait_for_speech_seconds: float | None
    speech_capture_wall_seconds: float | None
    vad_endpoint_delay_estimate_seconds: float
    post_vad_transcript_seconds: float | None
    post_vad_task_choice_seconds: float | None
    post_vad_memory_search_seconds: float | None
    post_vad_search_depth_seconds: float | None
    post_vad_memory_retrieval_seconds: float | None
    post_vad_memory_relevance_seconds: float | None
    post_vad_task_prompt_seconds: float | None
    post_vad_task_execution_seconds: float | None
    post_vad_primitive_dispatch_seconds: float | None
    post_vad_action_history_summary_seconds: float | None
    estimated_user_stop_to_transcript_seconds: float | None
    estimated_user_stop_to_task_choice_seconds: float | None
    estimated_user_stop_to_memory_search_seconds: float | None
    estimated_user_stop_to_search_depth_seconds: float | None
    estimated_user_stop_to_memory_retrieval_seconds: float | None
    estimated_user_stop_to_memory_relevance_seconds: float | None
    estimated_user_stop_to_task_prompt_seconds: float | None
    estimated_user_stop_to_task_execution_seconds: float | None
    estimated_user_stop_to_primitive_dispatch_seconds: float | None
    estimated_user_stop_to_action_history_summary_seconds: float | None
    transcription_seconds: float | None
    task_choice_seconds: float | None
    memory_search_seconds: float | None
    search_depth_seconds: float | None
    memory_retrieval_seconds: float | None
    memory_relevance_seconds: float | None
    task_prompt_seconds: float | None
    task_execution_seconds: float | None
    primitive_dispatch_seconds: float | None
    action_history_summary_seconds: float | None
    total_seconds: float

    def to_dict(self) -> dict[str, float | None]:
        return {
            "model_prepare_seconds": self.model_prepare_seconds,
            "keyphrase_wait_seconds": self.keyphrase_wait_seconds,
            "listen_seconds": self.listen_seconds,
            "wait_for_speech_seconds": self.wait_for_speech_seconds,
            "speech_capture_wall_seconds": self.speech_capture_wall_seconds,
            "vad_endpoint_delay_estimate_seconds": (
                self.vad_endpoint_delay_estimate_seconds
            ),
            "post_vad_transcript_seconds": self.post_vad_transcript_seconds,
            "post_vad_task_choice_seconds": self.post_vad_task_choice_seconds,
            "post_vad_memory_search_seconds": self.post_vad_memory_search_seconds,
            "post_vad_search_depth_seconds": self.post_vad_search_depth_seconds,
            "post_vad_memory_retrieval_seconds": (
                self.post_vad_memory_retrieval_seconds
            ),
            "post_vad_memory_relevance_seconds": (
                self.post_vad_memory_relevance_seconds
            ),
            "post_vad_task_prompt_seconds": self.post_vad_task_prompt_seconds,
            "post_vad_task_execution_seconds": (
                self.post_vad_task_execution_seconds
            ),
            "post_vad_primitive_dispatch_seconds": (
                self.post_vad_primitive_dispatch_seconds
            ),
            "post_vad_action_history_summary_seconds": (
                self.post_vad_action_history_summary_seconds
            ),
            "estimated_user_stop_to_transcript_seconds": (
                self.estimated_user_stop_to_transcript_seconds
            ),
            "estimated_user_stop_to_task_choice_seconds": (
                self.estimated_user_stop_to_task_choice_seconds
            ),
            "estimated_user_stop_to_memory_search_seconds": (
                self.estimated_user_stop_to_memory_search_seconds
            ),
            "estimated_user_stop_to_search_depth_seconds": (
                self.estimated_user_stop_to_search_depth_seconds
            ),
            "estimated_user_stop_to_memory_retrieval_seconds": (
                self.estimated_user_stop_to_memory_retrieval_seconds
            ),
            "estimated_user_stop_to_memory_relevance_seconds": (
                self.estimated_user_stop_to_memory_relevance_seconds
            ),
            "estimated_user_stop_to_task_prompt_seconds": (
                self.estimated_user_stop_to_task_prompt_seconds
            ),
            "estimated_user_stop_to_task_execution_seconds": (
                self.estimated_user_stop_to_task_execution_seconds
            ),
            "estimated_user_stop_to_primitive_dispatch_seconds": (
                self.estimated_user_stop_to_primitive_dispatch_seconds
            ),
            "estimated_user_stop_to_action_history_summary_seconds": (
                self.estimated_user_stop_to_action_history_summary_seconds
            ),
            "transcription_seconds": self.transcription_seconds,
            "task_choice_seconds": self.task_choice_seconds,
            "memory_search_seconds": self.memory_search_seconds,
            "search_depth_seconds": self.search_depth_seconds,
            "memory_retrieval_seconds": self.memory_retrieval_seconds,
            "memory_relevance_seconds": self.memory_relevance_seconds,
            "task_prompt_seconds": self.task_prompt_seconds,
            "task_execution_seconds": self.task_execution_seconds,
            "primitive_dispatch_seconds": self.primitive_dispatch_seconds,
            "action_history_summary_seconds": self.action_history_summary_seconds,
            "total_seconds": self.total_seconds,
        }


@dataclass(frozen=True)
class VoiceTurnResult:
    mode: types.ConversationMode
    mode_switched: bool
    keyphrase_detection: KeyphraseDetection | None
    trigger_detection: TriggerPhraseDetection | None
    routed_transcript: str
    ignored: bool
    utterance: DetectedUtterance | None
    transcript: Transcript | None
    task_choice: types.TaskChoiceDecision | None
    memory_search_hints: types.ConversationMemorySearchHints | None
    search_depths: types.SearchDepthDecision | None
    retrieved_memories: RetrievedMemoryContext | None
    relevance_decision: types.RelevantMemoryDecision | None
    relevant_memories: RetrievedMemoryContext | None
    selected_memory_contexts: list[types.TaskPromptSelectedMemoryContext] | None
    task_prompt: types.TaskPromptDecision | None
    task_execution: types.TaskExecutionResult | None
    primitive_dispatch: PrimitiveDispatchResult | None
    action_history_summary: str | None
    timings: VoiceTurnTimings

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "mode_switched": self.mode_switched,
            "keyphrase_detection": (
                {
                    "kind": self.keyphrase_detection.kind,
                    "phrase": self.keyphrase_detection.phrase,
                    "hypstr": self.keyphrase_detection.hypstr,
                    "confirmed": self.keyphrase_detection.confirmed,
                    "phrase_start_sample": (
                        self.keyphrase_detection.phrase_start_sample
                    ),
                    "phrase_end_sample": (
                        self.keyphrase_detection.phrase_end_sample
                    ),
                }
                if self.keyphrase_detection is not None
                else None
            ),
            "trigger_detection": (
                {
                    "kind": self.trigger_detection.kind,
                    "phrase": self.trigger_detection.phrase,
                    "routed_transcript": self.trigger_detection.routed_transcript,
                }
                if self.trigger_detection is not None
                else None
            ),
            "routed_transcript": self.routed_transcript,
            "ignored": self.ignored,
            "utterance": (
                {
                    "sample_rate": self.utterance.sample_rate,
                    "duration_seconds": self.utterance.duration_seconds,
                    "forced_end": self.utterance.forced_end,
                }
                if self.utterance is not None
                else None
            ),
            "transcript": (
                self.transcript.to_dict()
                if self.transcript is not None
                else None
            ),
            "task_choice": (
                self.task_choice.model_dump(mode="json")
                if self.task_choice is not None
                else None
            ),
            "memory_search_hints": (
                self.memory_search_hints.model_dump(mode="json")
                if self.memory_search_hints is not None
                else None
            ),
            "search_depths": (
                self.search_depths.model_dump(mode="json")
                if self.search_depths is not None
                else None
            ),
            "retrieved_memories": (
                self.retrieved_memories.to_dict()
                if self.retrieved_memories is not None
                else None
            ),
            "relevance_decision": (
                self.relevance_decision.model_dump(mode="json")
                if self.relevance_decision is not None
                else None
            ),
            "relevant_memories": (
                self.relevant_memories.to_dict()
                if self.relevant_memories is not None
                else None
            ),
            "selected_memory_contexts": (
                [
                    context.model_dump(mode="json")
                    for context in self.selected_memory_contexts
                ]
                if self.selected_memory_contexts is not None
                else None
            ),
            "task_prompt": (
                self.task_prompt.model_dump(mode="json")
                if self.task_prompt is not None
                else None
            ),
            "task_execution": (
                self.task_execution.model_dump(mode="json")
                if self.task_execution is not None
                else None
            ),
            "primitive_dispatch": (
                {
                    "task_history_id": self.primitive_dispatch.task_history_id,
                    "task_history_node_id": (
                        self.primitive_dispatch.task_history_node_id
                    ),
                    "records": [
                        {
                            "name": record.name,
                            "status": record.status,
                            "detail": record.detail,
                            "output": dict(record.output),
                        }
                        for record in self.primitive_dispatch.records
                    ]
                }
                if self.primitive_dispatch is not None
                else None
            ),
            "action_history_summary": (
                self.action_history_summary
                if self.action_history_summary is not None
                else None
            ),
            "timings": self.timings.to_dict(),
        }


@dataclass(frozen=True)
class CaptureResult:
    conversation_mode: types.ConversationMode
    keyphrase_detection: KeyphraseDetection | None
    utterance: DetectedUtterance | None
    mode_switched: bool
    keyphrase_wait_seconds: float | None
    listen_seconds: float
    wait_for_speech_seconds: float | None
    speech_capture_wall_seconds: float | None


@dataclass(frozen=True)
class CaptureStreamEvent:
    kind: CaptureStreamEventKind
    turn_id: int
    capture: CaptureResult | None = None


class VoiceTurnControl:
    def __init__(self) -> None:
        self._cancelled = asyncio.Event()
        self._committed = asyncio.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def commit(self) -> None:
        self._committed.set()

    async def checkpoint(self) -> None:
        if self._cancelled.is_set():
            raise asyncio.CancelledError

    async def wait_until_committed(self) -> None:
        if self._committed.is_set():
            await self.checkpoint()
            return

        commit_task = asyncio.create_task(self._committed.wait())
        cancel_task = asyncio.create_task(self._cancelled.wait())
        try:
            done, pending = await asyncio.wait(
                {commit_task, cancel_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if cancel_task in done:
                raise asyncio.CancelledError
        finally:
            for task in (commit_task, cancel_task):
                if not task.done():
                    task.cancel()
