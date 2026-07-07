from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import time
from typing import Any

from baml_core import Collector

from reframe_agent_host.agent_flow.memory_retrieval import (
    _search_hints,
    _timestamp_breadths,
)
from reframe_agent_host.agent_flow.relevance_candidates import (
    candidate_contexts,
    filter_retrieved_memories,
)
from reframe_agent_host.agent_flow.search_depth import default_search_domains
from reframe_agent_host.agent_flow.session_context import current_conversation_history
from reframe_agent_host.agent_flow.task_prompt import (
    build_task_prompt_decision,
    selected_memory_contexts,
)
from reframe_agent_host.agent_flow.timestamps import timestamp_fields
import baml_sdk as baml
import baml_sdk as types
from reframe_agent_host.agent_flow.baml_clients import client_kwargs
from reframe_agent_host.benchmarks.reasoning_efforts import (
    collector_stop_reason,
    collector_usage,
)
from reframe_agent_host.benchmarks.task_prompt_cases import TaskPromptBenchmarkCase
from reframe_agent_host.benchmarks.task_prompt_config import (
    TaskPromptBenchmarkConfig,
)
from reframe_agent_host.memory_seed import ensure_core_tasks
from reframe_memory import (
    Conversation,
    ConversationMessage,
    GraphMemoryRetriever,
    GraphRetrievalRequest,
    MemoryDatabase,
    RetrievedMemoryContext,
    Session,
    SessionMemory,
    TaskNode,
)


TASK_PROMPT_SNAPSHOT_DIR = Path("benchmark-results") / "task-prompt-snapshots"


@dataclass(frozen=True)
class TaskPromptSnapshot:
    case: TaskPromptBenchmarkCase
    current_timestamp: str
    session_id: str | None
    conversation_id: str | None
    task_choice: types.TaskChoiceDecision | None
    selected_task: types.SelectedTaskContext | None
    current_conversation: types.ConversationHistory | None
    session_memories: list[types.SessionMemoryContext]
    memory_search_hints: types.ConversationMemorySearchHints | None
    search_depths: types.SearchDepthDecision | None
    retrieved_memories: RetrievedMemoryContext | None
    relevance_decision: types.RelevantMemoryDecision | None
    selected_memories: RetrievedMemoryContext | None
    selected_memory_contexts: list[types.TaskPromptSelectedMemoryContext]
    task_prompt_memories: list[types.TaskPromptMemoryContext]
    latency_seconds: float
    stage_latency_seconds: dict[str, float]
    error: str | None = None

    @property
    def selected_task_id(self) -> str | None:
        if self.task_choice is None:
            return None
        return self.task_choice.selected_task_id

    @property
    def selected_task_name(self) -> str | None:
        if self.selected_task is None:
            return None
        return self.selected_task.name

    @property
    def task_correct(self) -> bool:
        return self.selected_task_name == self.case.expected_task_name


async def build_task_prompt_snapshot(
    database: MemoryDatabase,
    case: TaskPromptBenchmarkCase,
    client=None,
    refresh: bool = False,
) -> TaskPromptSnapshot:
    snapshot_path = _snapshot_path(case)
    if not refresh and snapshot_path.exists():
        return _load_snapshot(case, snapshot_path)

    snapshot = await _build_live_task_prompt_snapshot(database, case, client=client)
    if snapshot.error is None:
        _write_snapshot(snapshot, snapshot_path)
    return snapshot


async def _build_live_task_prompt_snapshot(
    database: MemoryDatabase,
    case: TaskPromptBenchmarkCase,
    client=None,
) -> TaskPromptSnapshot:
    started_at = time.perf_counter()
    current_timestamp = _current_timestamp()
    stage_latencies: dict[str, float] = {}
    task_choice = None
    selected_task = None
    memory_search_hints = None
    search_depths = None
    retrieved_memories = None
    relevance_decision = None
    selected_memories = None
    selected_contexts: list[types.TaskPromptSelectedMemoryContext] = []
    task_prompt_memories: list[types.TaskPromptMemoryContext] = []
    session_id = None
    conversation_id = None
    current_conversation = None

    try:
        await ensure_core_tasks(database)
        session_id, conversation_id = await _create_case_memory(database, case)

        current_conversation = await current_conversation_history(
            database,
            session_id,
            conversation_id,
        )
        session_memories = await _session_memories(database, session_id)
        available_tasks = await _core_available_tasks(database)
        task_choice_memories = await _task_choice_memories(database)

        task_choice, latency = await _choose_task(
            client,
            case,
            current_conversation,
            session_memories,
            available_tasks,
            task_choice_memories,
        )
        stage_latencies["task_choice"] = latency

        await _record_current_turn(database, conversation_id, case, task_choice)
        current_conversation = await current_conversation_history(
            database,
            session_id,
            conversation_id,
        )
        session_memories = await _session_memories(database, session_id)

        selected_task_node = await database.tasks.get(task_choice.selected_task_id)
        if selected_task_node is None:
            msg = f"selected task does not exist: {task_choice.selected_task_id}"
            raise ValueError(msg)
        selected_task = _selected_task_context(selected_task_node)

        memory_search_hints, latency = await _memory_search_hints(
            client,
            database,
            case,
            current_conversation,
            session_memories,
            selected_task,
        )
        stage_latencies["search_hints"] = latency

        search_depths, latency = await _search_depths(
            client,
            database,
            case,
            current_timestamp,
            current_conversation,
            session_memories,
            selected_task,
            memory_search_hints,
        )
        stage_latencies["search_depth"] = latency

        retrieved_memories, latency = await _retrieve_memories(
            database,
            session_id,
            memory_search_hints,
            search_depths,
        )
        stage_latencies["memory_retrieval"] = latency

        relevance_decision, latency = await _relevance_decision(
            client,
            database,
            case,
            session_id,
            current_conversation,
            session_memories,
            selected_task,
            retrieved_memories,
        )
        stage_latencies["memory_relevance"] = latency

        selected_memories = filter_retrieved_memories(
            retrieved_memories,
            relevance_decision,
        )
        selected_contexts = selected_memory_contexts(
            selected_memories,
            relevance_decision.kept_memory_ids,
        )
        task_prompt_memories = await _task_prompt_memories(database)
    except Exception as exc:
        return TaskPromptSnapshot(
            case=case,
            current_timestamp=current_timestamp,
            session_id=session_id,
            conversation_id=conversation_id,
            task_choice=task_choice,
            selected_task=selected_task,
            current_conversation=current_conversation,
            session_memories=(
                await _session_memories(database, session_id)
                if session_id is not None
                else []
            ),
            memory_search_hints=memory_search_hints,
            search_depths=search_depths,
            retrieved_memories=retrieved_memories,
            relevance_decision=relevance_decision,
            selected_memories=selected_memories,
            selected_memory_contexts=selected_contexts,
            task_prompt_memories=task_prompt_memories,
            latency_seconds=time.perf_counter() - started_at,
            stage_latency_seconds=stage_latencies,
            error=str(exc),
        )

    return TaskPromptSnapshot(
        case=case,
        current_timestamp=current_timestamp,
        session_id=session_id,
        conversation_id=conversation_id,
        task_choice=task_choice,
        selected_task=selected_task,
        current_conversation=current_conversation,
        session_memories=session_memories,
        memory_search_hints=memory_search_hints,
        search_depths=search_depths,
        retrieved_memories=retrieved_memories,
        relevance_decision=relevance_decision,
        selected_memories=selected_memories,
        selected_memory_contexts=selected_contexts,
        task_prompt_memories=task_prompt_memories,
        latency_seconds=time.perf_counter() - started_at,
        stage_latency_seconds=stage_latencies,
    )


async def run_task_prompt_case(
    client,
    provider,
    snapshot: TaskPromptSnapshot,
    run_index: int,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    case = snapshot.case
    collector = Collector(
        name=(
            f"task-prompt-{provider.id}-{reasoning_effort or 'default'}-"
            f"{case.id}-{run_index}"
        )
    )
    if snapshot.error is not None:
        return {
            "case_id": case.id,
            "run_index": run_index,
            "provider_id": provider.id,
            "reasoning_effort": reasoning_effort,
            "selected_task_id": snapshot.selected_task_id,
            "selected_task_name": snapshot.selected_task_name,
            "task_correct": snapshot.task_correct,
            "snapshot_error": True,
            "error": f"snapshot failed: {snapshot.error}",
            "latency_seconds": time.perf_counter() - started_at,
        }

    try:
        decision, prompt_latency = await task_prompt(client, snapshot)
    except Exception as exc:
        return {
            "case_id": case.id,
            "run_index": run_index,
            "provider_id": provider.id,
            "reasoning_effort": reasoning_effort,
            "selected_task_id": snapshot.selected_task_id,
            "selected_task_name": snapshot.selected_task_name,
            "task_correct": snapshot.task_correct,
            "error": str(exc),
            "latency_seconds": time.perf_counter() - started_at,
            "usage": collector_usage(collector),
            "stop_reason": collector_stop_reason(collector),
        }

    evaluation = evaluate_task_prompt(decision, snapshot)
    return {
        "case_id": case.id,
        "run_index": run_index,
        "provider_id": provider.id,
        "reasoning_effort": reasoning_effort,
        "selected_task_id": snapshot.selected_task_id,
        "selected_task_name": snapshot.selected_task_name,
        "task_correct": snapshot.task_correct,
        "correct": evaluation["correct"],
        "evaluation": evaluation,
        "task_prompt": decision.model_dump(mode="json"),
        "latency_seconds": prompt_latency,
        "stage_latency_seconds": {"task_prompt": prompt_latency},
        "usage": collector_usage(collector),
        "stop_reason": collector_stop_reason(collector),
    }


async def warmup_task_prompt(client, snapshots, config: TaskPromptBenchmarkConfig) -> int:
    errors = 0
    usable = [snapshot for snapshot in snapshots if snapshot.error is None]
    if config.warmup_runs < 1 or not usable:
        return errors

    for _ in range(config.warmup_runs):
        try:
            await task_prompt(client, usable[0])
        except Exception:
            errors += 1
        if config.delay_seconds > 0:
            await asyncio.sleep(config.delay_seconds)
    return errors


async def task_prompt(
    client,
    snapshot: TaskPromptSnapshot,
):
    started_at = time.perf_counter()
    composition = await baml.ComposeTaskInput_async(
        current_user_request=snapshot.case.current_user_request,
        current_conversation=snapshot.current_conversation,
        session_memories=snapshot.session_memories,
        selected_task=snapshot.selected_task,
        selected_memories=snapshot.selected_memory_contexts,
        task_prompt_memories=snapshot.task_prompt_memories,
        **client_kwargs(client),
    )
    result = build_task_prompt_decision(snapshot.selected_task.prompt, composition)
    return result, time.perf_counter() - started_at


def evaluate_task_prompt(
    decision: types.TaskPromptDecision,
    snapshot: TaskPromptSnapshot,
) -> dict[str, Any]:
    parsed = parse_task_prompt(decision.full_task_prompt)
    input_text = parsed["input"]
    task_text = parsed["task"]
    task_present = bool(task_text.strip())
    input_present = bool(input_text.strip())
    correct = parsed["shape_ok"] and task_present and input_present
    return {
        "correct": correct,
        "structural_pass": correct,
        "shape_ok": parsed["shape_ok"],
        "top_level_labels": parsed["top_level_labels"],
        "task_present": task_present,
        "input_present": input_present,
    }


def parse_task_prompt(text: str) -> dict[str, Any]:
    labels = _top_level_labels(text)
    match = re.match(r"(?is)^\s*Task:\s*(.*?)\n\s*Input:\s*(.*?)\s*$", text)
    return {
        "shape_ok": match is not None and labels == ["Task", "Input"],
        "top_level_labels": labels,
        "task": match.group(1) if match else "",
        "input": match.group(2) if match else "",
    }


def snapshot_payload(snapshot: TaskPromptSnapshot) -> dict[str, Any]:
    payload = {
        "case_id": snapshot.case.id,
        "current_timestamp": snapshot.current_timestamp,
        "current_user_request": snapshot.case.current_user_request,
        "expected_task_name": snapshot.case.expected_task_name,
        "selected_task_id": snapshot.selected_task_id,
        "selected_task_name": snapshot.selected_task_name,
        "task_correct": snapshot.task_correct,
        "latency_seconds": snapshot.latency_seconds,
        "stage_latency_seconds": dict(snapshot.stage_latency_seconds),
        "task_prompt_input_snapshot": {
            "session_id": snapshot.session_id,
            "conversation_id": snapshot.conversation_id,
            "task_choice": _dump_model(snapshot.task_choice),
            "selected_task": _dump_model(snapshot.selected_task),
            "current_conversation": _dump_model(snapshot.current_conversation),
            "session_memories": _dump_models(snapshot.session_memories),
            "memory_search_hints": _dump_model(snapshot.memory_search_hints),
            "search_depths": _dump_model(snapshot.search_depths),
            "retrieved_memories": (
                snapshot.retrieved_memories.to_dict()
                if snapshot.retrieved_memories is not None
                else None
            ),
            "relevance_decision": _dump_model(snapshot.relevance_decision),
            "selected_memories": _dump_models(snapshot.selected_memory_contexts),
            "task_prompt_memories": _dump_models(snapshot.task_prompt_memories),
        },
    }
    if snapshot.error is not None:
        payload["error"] = snapshot.error
    return payload


def _snapshot_path(case: TaskPromptBenchmarkCase) -> Path:
    return TASK_PROMPT_SNAPSHOT_DIR / f"{case.id}.json"


def _write_snapshot(snapshot: TaskPromptSnapshot, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(snapshot_payload(snapshot), indent=2) + "\n",
        encoding="utf-8",
    )


def _load_snapshot(
    case: TaskPromptBenchmarkCase,
    path: Path,
) -> TaskPromptSnapshot:
    payload = json.loads(path.read_text(encoding="utf-8"))
    prompt_input = payload["task_prompt_input_snapshot"]
    return TaskPromptSnapshot(
        case=case,
        current_timestamp=str(payload.get("current_timestamp") or ""),
        session_id=prompt_input.get("session_id"),
        conversation_id=prompt_input.get("conversation_id"),
        task_choice=_model_or_none(
            types.TaskChoiceDecision,
            prompt_input.get("task_choice"),
        ),
        selected_task=_model_or_none(
            types.SelectedTaskContext,
            prompt_input.get("selected_task"),
        ),
        current_conversation=_model_or_none(
            types.ConversationHistory,
            prompt_input["current_conversation"],
        ),
        session_memories=[
            types.SessionMemoryContext(**memory)
            for memory in prompt_input.get("session_memories", [])
        ],
        memory_search_hints=_model_or_none(
            types.ConversationMemorySearchHints,
            prompt_input.get("memory_search_hints"),
        ),
        search_depths=_model_or_none(
            types.SearchDepthDecision,
            prompt_input.get("search_depths"),
        ),
        retrieved_memories=None,
        relevance_decision=_model_or_none(
            types.RelevantMemoryDecision,
            prompt_input.get("relevance_decision"),
        ),
        selected_memories=None,
        selected_memory_contexts=[
            types.TaskPromptSelectedMemoryContext(**memory)
            for memory in prompt_input.get("selected_memories", [])
        ],
        task_prompt_memories=[
            types.TaskPromptMemoryContext(**memory)
            for memory in prompt_input.get("task_prompt_memories", [])
        ],
        latency_seconds=float(payload.get("latency_seconds") or 0.0),
        stage_latency_seconds=dict(payload.get("stage_latency_seconds") or {}),
        error=payload.get("error"),
    )


def _model_or_none(model, payload):
    if payload is None:
        return None
    return model(**payload)


async def _create_case_memory(
    database: MemoryDatabase,
    case: TaskPromptBenchmarkCase,
) -> tuple[str, str]:
    suffix = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    session = await database.sessions.create(
        Session(name=f"Task prompt benchmark {case.id} {suffix}"),
        tags=("benchmark", "task-prompt", case.id),
    )
    conversation = await database.conversations.create(
        session.id,
        Conversation(name=case.conversation_name),
        tags=("benchmark", "task-prompt", case.id),
    )
    for position, message in enumerate(case.messages):
        await database.conversations.add_message(
            conversation.id,
            ConversationMessage(role=message.role, content=message.content),
            tags=("benchmark", "task-prompt", case.id),
            position=position,
        )
    for memory in case.session_memories:
        await database.session_memories.create(
            session.id,
            SessionMemory(title=memory.title, description=memory.description),
            tags=("benchmark", "task-prompt", case.id, *memory.tags),
        )
    return session.id, conversation.id


async def _record_current_turn(
    database: MemoryDatabase,
    conversation_id: str,
    case: TaskPromptBenchmarkCase,
    task_choice: types.TaskChoiceDecision,
) -> None:
    await database.conversations.add_message(
        conversation_id,
        ConversationMessage(role="human", content=case.current_user_request),
        tags=("benchmark", "task-prompt", case.id),
    )
    thought = (task_choice.agent_thought or "").strip()
    if thought:
        await database.conversations.add_message(
            conversation_id,
            ConversationMessage(role="agent_thought", content=thought),
            tags=("benchmark", "task-prompt", case.id),
        )


async def _choose_task(
    client,
    case,
    current_conversation,
    session_memories,
    available_tasks,
    task_choice_memories,
):
    started_at = time.perf_counter()
    result = await baml.ChooseTask_async(
        current_user_request=case.current_user_request,
        current_conversation=current_conversation,
        session_memories=session_memories,
        available_tasks=available_tasks,
        task_choice_memories=task_choice_memories,
        **client_kwargs(client),
    )
    return result, time.perf_counter() - started_at


async def _memory_search_hints(
    client,
    database,
    case,
    current_conversation,
    session_memories,
    selected_task,
):
    started_at = time.perf_counter()
    result = await baml.ChooseMemorySearch_async(
        current_user_request=case.current_user_request,
        current_conversation=current_conversation,
        session_memories=session_memories,
        selected_task=selected_task,
        conversation_evaluation_memories=await _conversation_evaluation_memories(
            database
        ),
        **client_kwargs(client),
    )
    return result, time.perf_counter() - started_at


async def _search_depths(
    client,
    database,
    case,
    current_timestamp,
    current_conversation,
    session_memories,
    selected_task,
    memory_search_hints,
):
    started_at = time.perf_counter()
    result = await baml.ChooseMemorySearchDepths_async(
        current_timestamp=current_timestamp,
        current_user_request=case.current_user_request,
        current_conversation=current_conversation,
        session_memories=session_memories,
        selected_task=selected_task,
        memory_search_hints=memory_search_hints,
        search_domains=default_search_domains(),
        search_depth_memories=await _search_depth_memories(database),
        **client_kwargs(client),
    )
    return result, time.perf_counter() - started_at


async def _retrieve_memories(
    database,
    session_id,
    memory_search_hints,
    search_depths,
):
    started_at = time.perf_counter()
    retriever = GraphMemoryRetriever(database, current_session_id=session_id)
    result = await retriever.retrieve(
        GraphRetrievalRequest(
            hints=_search_hints(memory_search_hints),
            depths=_timestamp_breadths(search_depths),
        )
    )
    return result, time.perf_counter() - started_at


async def _relevance_decision(
    client,
    database,
    case,
    session_id,
    current_conversation,
    session_memories,
    selected_task,
    retrieved_memories,
):
    started_at = time.perf_counter()
    result = await baml.SelectRelevantMemories_async(
        current_user_request=case.current_user_request,
        current_conversation=current_conversation,
        session_memories=session_memories,
        selected_task=selected_task,
        candidate_memories=candidate_contexts(
            retrieved_memories,
            current_session_id=session_id,
        ),
        relevance_memories=await _relevance_memories(database),
        **client_kwargs(client),
    )
    return result, time.perf_counter() - started_at


async def _core_available_tasks(database) -> list[types.AvailableTask]:
    seed = await ensure_core_tasks(database)
    tasks = []
    seen_task_ids = set()
    for provider_id in seed.provider_ids:
        for task in await database.providers.tasks_for(provider_id):
            if task.id in seen_task_ids:
                continue
            seen_task_ids.add(task.id)
            tasks.append(task)
    return [
        types.AvailableTask(
            id=task.id,
            name=task.content.name,
            description=task.content.description,
            input=task.content.input,
            output=task.content.output,
            prompt=task.content.prompt,
            provider_id=task.content.provider_id,
            **timestamp_fields(task),
        )
        for task in tasks
    ]


def _selected_task_context(task: TaskNode) -> types.SelectedTaskContext:
    return types.SelectedTaskContext(
        id=task.id,
        name=task.content.name,
        description=task.content.description,
        input=task.content.input,
        output=task.content.output,
        prompt=task.content.prompt,
        provider_id=task.content.provider_id,
        **timestamp_fields(task),
    )


async def _session_memories(database, session_id) -> list[types.SessionMemoryContext]:
    memories = await database.session_memories.for_session(session_id)
    return [
        types.SessionMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in memories
    ]


async def _task_choice_memories(database) -> list[types.TaskChoiceMemoryContext]:
    memories = await database.task_choice_memories.search()
    return [
        types.TaskChoiceMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in memories
    ]


async def _conversation_evaluation_memories(
    database,
) -> list[types.ConversationEvaluationMemoryContext]:
    memories = await database.conversation_evaluation_memories.search()
    return [
        types.ConversationEvaluationMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in memories
    ]


async def _search_depth_memories(database) -> list[types.SearchDepthMemoryContext]:
    memories = await database.search_depth_memories.search()
    return [
        types.SearchDepthMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in memories
    ]


async def _relevance_memories(database) -> list[types.RelevanceMemoryContext]:
    memories = await database.relevance_memories.search()
    return [
        types.RelevanceMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in memories
    ]


async def _task_prompt_memories(database) -> list[types.TaskPromptMemoryContext]:
    memories = await database.task_prompt_memories.search()
    return [
        types.TaskPromptMemoryContext(
            title=memory.content.title,
            description=memory.content.description,
            tags=list(memory.tags),
            **timestamp_fields(memory),
        )
        for memory in memories
    ]


def _current_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _top_level_labels(text: str) -> list[str]:
    labels = []
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z][A-Za-z -]*):\s*$", line)
        if match:
            labels.append(match.group(1))
    return labels


def _dump_models(values: list[Any]) -> list[Any]:
    return [_dump_model(value) for value in values]


def _dump_model(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value
