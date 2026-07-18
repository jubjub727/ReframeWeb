from __future__ import annotations

from importlib import import_module
from typing import Any, Callable, Final


HANDLER_MODULES: Final[dict[str, str]] = {
    "run_audio_devices": "reframe_agent_host.commands.checks",
    "run_doctor": "reframe_agent_host.commands.checks",
    "run_gpu_check": "reframe_agent_host.commands.checks",
    "run_transcription_check": "reframe_agent_host.commands.checks",
    "run_analyze_conversation_evaluation_benchmark": (
        "reframe_agent_host.commands.conversation_evaluation"
    ),
    "run_benchmark_conversation_evaluation": (
        "reframe_agent_host.commands.conversation_evaluation"
    ),
    "run_analyze_control_flow_benchmark": (
        "reframe_agent_host.commands.control_flow"
    ),
    "run_benchmark_control_flow": "reframe_agent_host.commands.control_flow",
    "run_benchmark_memory_relevance": (
        "reframe_agent_host.commands.memory_relevance"
    ),
    "run_memory_browser": "reframe_agent_host.commands.memory_browser",
    "run_benchmark_task_prompt": "reframe_agent_host.commands.task_prompt",
    "run_audio_quality_test": "reframe_agent_host.commands.audio_quality_test",
    "run_benchmark_task_choice": "reframe_agent_host.commands.task_choice",
    "run_analyze_task_choice_benchmark": (
        "reframe_agent_host.commands.task_choice"
    ),
    "run_choose_task": "reframe_agent_host.commands.task_choice",
    "run_list_opencode_go_models": "reframe_agent_host.commands.task_choice",
    "run_memory_setup": "reframe_agent_host.commands.task_choice",
    "run_seed_core_tasks": "reframe_agent_host.commands.task_choice",
    "run_seed_opencode_go_providers": "reframe_agent_host.commands.task_choice",
    "run_voice_turn": "reframe_agent_host.commands.voice_turn",
    "run_workspace": "reframe_agent_host.commands.workspace",
    "run_debug_wake_audio": "reframe_agent_host.commands.debug_wake_audio",
    "run_record_wake_audio": "reframe_agent_host.commands.record_wake_audio",
}


def load_handler(name: str) -> Callable[..., Any]:
    return getattr(import_module(HANDLER_MODULES[name]), name)
