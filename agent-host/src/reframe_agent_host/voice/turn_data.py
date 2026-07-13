from __future__ import annotations

from dataclasses import asdict, dataclass

from baml_sdk import turn_context as baml_turn_context
from baml_sdk import memory as baml_memory
from baml_sdk import task as baml_task
from reframe_agent_host.keyphrases import KeyphraseDetection
from reframe_agent_host.speech.transcription import Transcript
from reframe_agent_host.speech.triggers import TriggerPhraseDetection
from reframe_agent_host.task_execution import PrimitiveDispatchResult
from reframe_agent_host.voice.activity import DetectedUtterance
from reframe_memory import RetrievedMemoryContext


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
    post_vad_task_completion_seconds: float | None
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
    estimated_user_stop_to_task_completion_seconds: float | None
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
    task_completion_seconds: float | None
    total_seconds: float

    def to_dict(self) -> dict[str, float | None]:
        return asdict(self)


@dataclass(frozen=True)
class VoiceTurnResult:
    mode: baml_turn_context.ConversationMode
    mode_switched: bool
    keyphrase_detection: KeyphraseDetection | None
    trigger_detection: TriggerPhraseDetection | None
    routed_transcript: str
    ignored: bool
    utterance: DetectedUtterance | None
    transcript: Transcript | None
    task_choice: baml_task.TaskChoiceDecision | None
    memory_search_hints: baml_memory.ConversationMemorySearchHints | None
    search_depths: baml_memory.SearchDepthDecision | None
    retrieved_memories: RetrievedMemoryContext | None
    relevance_decision: baml_memory.RelevantMemoryDecision | None
    relevant_memories: RetrievedMemoryContext | None
    selected_memory_contexts: list[baml_task.TaskPromptSelectedMemoryContext] | None
    task_prompt: baml_task.TaskPromptDecision | None
    task_execution: baml_task.TaskExecutionResult | None
    primitive_dispatch: PrimitiveDispatchResult | None
    action_history_summary: str | None
    task_completion: baml_task.CompletionResult | None
    timings: VoiceTurnTimings

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "mode_switched": self.mode_switched,
            "keyphrase_detection": _keyphrase_dict(self.keyphrase_detection),
            "trigger_detection": _trigger_dict(self.trigger_detection),
            "routed_transcript": self.routed_transcript,
            "ignored": self.ignored,
            "utterance": _utterance_dict(self.utterance),
            "transcript": None if self.transcript is None else self.transcript.to_dict(),
            "task_choice": _model_dict(self.task_choice),
            "memory_search_hints": _model_dict(self.memory_search_hints),
            "search_depths": _model_dict(self.search_depths),
            "retrieved_memories": _context_dict(self.retrieved_memories),
            "relevance_decision": _model_dict(self.relevance_decision),
            "relevant_memories": _context_dict(self.relevant_memories),
            "selected_memory_contexts": (
                None
                if self.selected_memory_contexts is None
                else [item.model_dump(mode="json") for item in self.selected_memory_contexts]
            ),
            "task_prompt": _model_dict(self.task_prompt),
            "task_execution": _model_dict(self.task_execution),
            "primitive_dispatch": _dispatch_dict(self.primitive_dispatch),
            "action_history_summary": self.action_history_summary,
            "task_completion": (
                None if self.task_completion is None else self.task_completion.value
            ),
            "timings": self.timings.to_dict(),
        }


def _model_dict(value):
    return None if value is None else value.model_dump(mode="json")


def _context_dict(value):
    return None if value is None else value.to_dict()


def _keyphrase_dict(value):
    if value is None:
        return None
    return {
        "kind": value.kind,
        "phrase": value.phrase,
        "hypstr": value.hypstr,
        "confirmed": value.confirmed,
        "phrase_start_sample": value.phrase_start_sample,
        "phrase_end_sample": value.phrase_end_sample,
    }


def _trigger_dict(value):
    if value is None:
        return None
    return {
        "kind": value.kind,
        "phrase": value.phrase,
        "routed_transcript": value.routed_transcript,
    }


def _utterance_dict(value):
    if value is None:
        return None
    return {
        "sample_rate": value.sample_rate,
        "duration_seconds": value.duration_seconds,
        "forced_end": value.forced_end,
    }


def _dispatch_dict(value):
    if value is None:
        return None
    return {
        "task_history_id": value.task_history_id,
        "task_history_node_id": value.task_history_node_id,
        "records": [
            {
                "name": record.name,
                "status": record.status,
                "detail": record.detail,
                "output": dict(record.output),
            }
            for record in value.records
        ],
    }
