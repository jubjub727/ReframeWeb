from __future__ import annotations

from collections import Counter

from reframe_agent_host.commands.memory_output import (
    memory_search_summary,
    memory_type_counts_summary,
    search_depth_summary,
    selected_memory_type_counts_summary,
)
from reframe_agent_host.commands.voice_output import latency, single_line
from reframe_agent_host.voice.pipeline_config import VoicePipelineConfig
from reframe_memory import (
    ConversationMessageNode,
    MemoryNode,
    RetrievedConversation,
    RetrievedMemoryContext,
    RetrievedSessionContext,
    SessionMemoryNode,
    TaskNode,
)


def print_turn_result(
    result,
    config: VoicePipelineConfig,
    *,
    debug_output: bool,
    verbose_context: bool,
) -> None:
    if not debug_output:
        return

    print("\nTurn summary")
    print(f"session_id: {config.session_id or 'NONE'}")
    print(f"conversation_id: {config.conversation_id or 'NONE'}")
    if result.routed_transcript:
        print(f"human_reply: {single_line(result.routed_transcript)}")
    _print_flow_summary(result, config, verbose_context)


def _print_flow_summary(result, config, verbose_context: bool) -> None:
    if result.transcript is not None:
        print(f"transcription: {latency(result.timings.transcription_seconds)}")
    if result.task_choice is not None:
        print(
            "task_choice: "
            f"{result.task_choice.selected_task_id} "
            f"confidence={result.task_choice.confidence:.2f} "
            f"latency={latency(result.timings.task_choice_seconds)}"
        )
    if result.memory_search_hints is not None:
        print(
            f"memory_search_terms: {memory_search_summary(result.memory_search_hints)} "
            f"latency={latency(result.timings.memory_search_seconds)}"
        )
    if result.search_depths is not None:
        print(
            f"search_depth: {search_depth_summary(result.search_depths)} "
            f"latency={latency(result.timings.search_depth_seconds)}"
        )
    _print_memory_summary(result, config, verbose_context)
    _print_task_summary(result)


def _print_memory_summary(result, config, verbose_context: bool) -> None:
    if result.retrieved_memories is not None:
        counts = memory_type_counts_summary(
            result.retrieved_memories, config.session_id
        )
        print(
            f"memory_candidates_by_type: {counts} "
            f"latency={latency(result.timings.memory_retrieval_seconds)}"
        )
        if verbose_context:
            _print_retrieved_memories(result.retrieved_memories)
    if result.relevance_decision is not None:
        print(
            f"memory_relevance: kept_ids={result.relevance_decision.kept_memory_ids} "
            f"latency={latency(result.timings.memory_relevance_seconds)}"
        )
    if result.relevant_memories is not None:
        print(
            "selected_memories_by_type: "
            f"{_selected_memory_counts(result, config.session_id)}"
        )
        context_summary = _selected_context_summary(result)
        if context_summary is not None:
            print(f"task_prompt_selected_contexts: {context_summary}")
        if verbose_context:
            _print_retrieved_memories(result.relevant_memories, "Relevant memories")


def _print_task_summary(result) -> None:
    if result.task_prompt is not None:
        print(
            f"task_prompt: chars={len(result.task_prompt.full_task_prompt)} "
            f"latency={latency(result.timings.task_prompt_seconds)}"
        )
    if result.task_execution is not None:
        print(
            f"task_execution: returns={len(result.task_execution.returns)} "
            f"latency={latency(result.timings.task_execution_seconds)}"
        )
    if result.primitive_dispatch is not None:
        print(
            f"response_items: records={len(result.primitive_dispatch.records)} "
            f"latency={latency(result.timings.primitive_dispatch_seconds)}"
        )
        if result.primitive_dispatch.task_history_id is not None:
            print(
                f"task_history: id={result.primitive_dispatch.task_history_id} "
                f"node={result.primitive_dispatch.task_history_node_id or 'NONE'}"
            )
        _print_conversation_returns(result.primitive_dispatch.records)
    if result.action_history_summary is not None:
        print(
            f"action_history_summary: chars={len(result.action_history_summary)} "
            f"latency={latency(result.timings.action_history_summary_seconds)}"
        )
    if result.task_completion is not None:
        print(
            f"task_completion: {result.task_completion.value} "
            f"latency={latency(result.timings.task_completion_seconds)}"
        )


def _selected_memory_counts(result, current_session_id: str | None) -> str | None:
    decision = getattr(result, "relevance_decision", None)
    retrieved = getattr(result, "retrieved_memories", None)
    if decision is not None and retrieved is not None:
        return selected_memory_type_counts_summary(
            retrieved,
            getattr(decision, "kept_memory_ids", ()),
            current_session_id,
        )
    relevant = getattr(result, "relevant_memories", None)
    if relevant is not None:
        return memory_type_counts_summary(relevant, current_session_id)
    return None


def _selected_context_summary(result) -> str | None:
    contexts = getattr(result, "selected_memory_contexts", None)
    if contexts is None:
        return None
    titles = Counter(context.title for context in contexts)
    messages = sum(count for title, count in titles.items() if title.endswith(" message"))
    sessions = sum(
        count
        for title, count in titles.items()
        if title.startswith(("Current session:", "Past session:"))
    )
    conversations = sum(
        count
        for title, count in titles.items()
        if title.startswith(("Current conversation:", "Past conversation:"))
    )
    roles = {
        role: titles.get(f"{role} message", 0)
        for role in (
            "human",
            "agent",
            "agent_thought",
            "agent_reply_interrupted",
            "validation_reply",
        )
    }
    return (
        f"total={len(contexts)} session_contexts={sessions} "
        f"conversation_contexts={conversations} message_contexts={messages} "
        f"human_message={roles['human']} agent_message={roles['agent']} "
        f"agent_thought_message={roles['agent_thought']} "
        f"agent_reply_interrupted_message={roles['agent_reply_interrupted']} "
        f"validation_reply_message={roles['validation_reply']} "
        f"other={len(contexts) - messages} "
        f"description_chars={sum(len(item.description) for item in contexts)}"
    )


def _print_conversation_returns(records) -> None:
    for record in records:
        if record.name in {"agent_thought", "agent_reply"}:
            print(f"{record.name}: {single_line(record.detail)}")
        elif record.status in {"unsupported", "malformed"}:
            print(f"agent_reply: {single_line(record.detail)}")


def _print_retrieved_memories(
    memories: RetrievedMemoryContext,
    label: str = "Retrieved memories",
) -> None:
    print(f"\n{label}")
    _print_session_memories(
        "Current session memories", memories.current_session_memories
    )
    _print_tasks(memories.task_catalog.tasks)
    _print_past_sessions(memories.past_conversation_context.sessions)


def _print_tasks(tasks: tuple[TaskNode, ...]) -> None:
    print(f"\nTask catalog ({len(tasks)})")
    if not tasks:
        print("  none")
        return
    for task in tasks:
        print(f"  - {task.content.name} [{task.id}]")
        print(f"    tags: {_tags(task)}")
        print(f"    description: {single_line(task.content.description)}")
        print(f"    input: {single_line(task.content.input)}")
        print(f"    output: {single_line(task.content.output)}")


def _print_past_sessions(sessions: tuple[RetrievedSessionContext, ...]) -> None:
    print(f"\nPast conversation context ({len(sessions)} sessions)")
    if not sessions:
        print("  none")
        return
    for session in sessions:
        marker = "matched" if session.matched else "wrapper"
        print(f"  - Session {session.session.content.name} [{session.session.id}] {marker}")
        _print_session_memories("    Session memories", session.session_memories)
        _print_conversations(session.conversations)


def _print_conversations(conversations: tuple[RetrievedConversation, ...]) -> None:
    print(f"    Conversations ({len(conversations)})")
    if not conversations:
        print("      none")
        return
    for conversation in conversations:
        marker = "matched" if conversation.matched else "wrapper"
        node = conversation.conversation
        print(f"      - {node.content.name} [{node.id}] {marker}")
        print(f"        messages ({len(conversation.messages)})")
        if not conversation.messages:
            print("          none")
        for message in conversation.messages:
            _print_message(message)


def _print_message(message: ConversationMessageNode) -> None:
    print(
        f"          - [{message.content.role}] {message.id}: "
        f"{single_line(message.content.content)}"
    )


def _print_session_memories(label: str, memories: tuple[SessionMemoryNode, ...]) -> None:
    print(f"\n{label} ({len(memories)})")
    if not memories:
        print("  none")
        return
    for memory in memories:
        print(f"  - {memory.content.title} [{memory.id}]")
        print(f"    tags: {_tags(memory)}")
        print(f"    description: {single_line(memory.content.description)}")


def _tags(node: MemoryNode[object]) -> str:
    return ", ".join(node.tags) if node.tags else "none"
