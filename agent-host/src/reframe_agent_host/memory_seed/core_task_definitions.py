from __future__ import annotations

from dataclasses import dataclass

from reframe_agent_host.magic_providers import MAGIC_DO_NOTHING_MODEL_ID
from reframe_memory import Task


@dataclass(frozen=True)
class CoreTaskDefinition:
    name: str
    description: str
    input: str
    output: str
    prompt: str
    tags: tuple[str, ...]
    model_id: str
    reasoning_effort: str | None

    def to_task(self, provider_id: str) -> Task:
        return Task(
            name=self.name,
            description=self.description,
            input=self.input,
            output=self.output,
            prompt=self.prompt,
            provider_id=provider_id,
        )


CORE_TASKS: tuple[CoreTaskDefinition, ...] = (
    CoreTaskDefinition(
        name="Explain request cannot be handled",
        description=(
            "Use when the most useful response is a clear limitation, "
            "boundary, or next-best path."
        ),
        input="The user's request.",
        output=(
            "Named return items that give the user a clear limitation or next "
            "step."
        ),
        prompt=(
            "Give the human a clear, brief explanation of the relevant "
            "limitation or boundary. Offer the most useful next step when one "
            "is available.\n\n"
            "Allowed return items:\n"
            "- agent_reply with payload {\"text\": \"...\"} for the message "
            "the user should hear.\n"
            "- agent_thought with payload {\"text\": \"...\"} for useful "
            "private context that belongs in the conversation.\n"
            "- session_memory with payload {\"title\": \"...\", "
            "\"description\": \"...\"} when the request reveals useful "
            "context for this session.\n"
            "- user_preference with payload {\"title\": \"...\", "
            "\"description\": \"...\"} when the request reveals a durable "
            "user preference or user-relevant information."
        ),
        tags=("limitation", "boundary"),
        model_id="glm-5.1",
        reasoning_effort="none",
    ),
    CoreTaskDefinition(
        name="Request more information from the user",
        description=(
            "Use when a useful next step depends on one specific piece of "
            "input from the human."
        ),
        input="The user's request.",
        output=(
            "Named return items that ask for the information needed to "
            "continue."
        ),
        prompt=(
            "Ask the human for the information needed to continue. Ask for the "
            "smallest useful piece of information, and make the next answer "
            "easy to provide.\n\n"
            "Allowed return items:\n"
            "- agent_reply with payload {\"text\": \"...\"} for the question "
            "the user should hear.\n"
            "- agent_thought with payload {\"text\": \"...\"} for useful "
            "private context that belongs in the conversation.\n"
            "- session_memory with payload {\"title\": \"...\", "
            "\"description\": \"...\"} when the request reveals useful "
            "context for this session.\n"
            "- user_preference with payload {\"title\": \"...\", "
            "\"description\": \"...\"} when the request reveals a durable "
            "user preference or user-relevant information."
        ),
        tags=("needs-information",),
        model_id="glm-5.1",
        reasoning_effort="none",
    ),
    CoreTaskDefinition(
        name="Turn conversation mode off",
        description=(
            "Use when the user asks the assistant to stop staying in "
            "continuous conversation or to wait until they address it again."
        ),
        input="The user's request to end continuous conversation.",
        output="Named return items that end continuous conversation.",
        prompt=(
            "End continuous conversation so the assistant goes quiet until the "
            "user addresses it again. Give a short confirmation when that "
            "would feel natural.\n\n"
            "Allowed return items:\n"
            "- conversation_mode_off with empty payload {} to end continuous "
            "conversation.\n"
            "- agent_reply with payload {\"text\": \"...\"} for a brief "
            "confirmation the user should hear.\n"
            "- agent_thought with payload {\"text\": \"...\"} for useful "
            "private context that belongs in the conversation."
        ),
        tags=("conversation-mode", "conversation-off"),
        model_id="kimi-k2.6",
        reasoning_effort="none",
    ),
    CoreTaskDefinition(
        name="Thinking",
        description=(
            "Use when the useful work is private thinking, recording context, "
            "or updating memory without speaking to the user."
        ),
        input="The user's request or conversational context.",
        output=(
            "Named non-spoken return items that record useful thought, session "
            "context, or durable user preference."
        ),
        prompt=(
            "Think privately about the supplied request or context. Use this "
            "task only for useful non-spoken work: preserving internal context, "
            "noting a relevant thought, or recording memory. If there is "
            "nothing useful to record, return an empty returns array.\n\n"
            "Allowed return items:\n"
            "- agent_thought with payload {\"text\": \"...\"} for useful "
            "private context that belongs in the conversation.\n"
            "- session_memory with payload {\"title\": \"...\", "
            "\"description\": \"...\"} when the exchange reveals useful "
            "context for this session.\n"
            "- user_preference with payload {\"title\": \"...\", "
            "\"description\": \"...\"} when the exchange reveals a durable "
            "user preference or user-relevant information."
        ),
        tags=("thinking", "silent", "memory"),
        model_id="glm-5.1",
        reasoning_effort="none",
    ),
    CoreTaskDefinition(
        name="Do nothing",
        description=(
            "Use when the correct response is to take no action, say nothing, "
            "and record nothing."
        ),
        input="The user's request or conversational context.",
        output="An empty returns array.",
        prompt=(
            "Do nothing. Return an empty returns array.\n"
        ),
        tags=("nothing", "silent"),
        model_id=MAGIC_DO_NOTHING_MODEL_ID,
        reasoning_effort=None,
    ),
    CoreTaskDefinition(
        name="Greeting",
        description=(
            "Use when the user's message is a simple greeting, check-in, or "
            "conversational opener."
        ),
        input="The user's greeting or conversational opener.",
        output="A named return item that greets the user naturally.",
        prompt=(
            "Respond naturally to the human's greeting or conversational "
            "opener. Keep it brief, warm, and style-matched. Do not turn a "
            "simple greeting into a broad follow-up unless that would clearly "
            "be useful.\n\n"
            "Allowed return items only:\n"
            "- agent_reply with payload {\"text\": \"...\"} for the greeting "
            "the user should hear.\n"
            "Use only the item type listed above."
        ),
        tags=("greeting", "reply"),
        model_id="glm-5.1",
        reasoning_effort="none",
    ),
    CoreTaskDefinition(
        name="Reply to user",
        description=(
            "Use when the user wants a conversational answer and the useful "
            "result is simply something said back to them. Do not reply "
            "simply for the sake of replying."
        ),
        input="The user's message.",
        output="Named return items that reply to the user.",
        prompt=(
            "Answer the human directly using the supplied request. Keep the "
            "reply concise, conversational, and useful.\n"
            "Do not return agent_reply just to acknowledge that a request was "
            "heard. Only return agent_reply when there is a useful spoken "
            "message for the human. If no spoken reply is useful, return only "
            "the relevant non-spoken items, or an empty returns array when "
            "there is nothing useful to record. Only reply when it's "
            "appropriate.\n\n"
            "Allowed return items:\n"
            "- agent_reply with payload {\"text\": \"...\"} for the message "
            "the user should hear.\n"
            "- agent_thought with payload {\"text\": \"...\"} for useful "
            "private context that belongs in the conversation.\n"
            "- session_memory with payload {\"title\": \"...\", "
            "\"description\": \"...\"} when the exchange reveals useful "
            "context for this session.\n"
            "- user_preference with payload {\"title\": \"...\", "
            "\"description\": \"...\"} when the exchange reveals a durable "
            "user preference or user-relevant information."
        ),
        tags=("reply",),
        model_id="glm-5.1",
        reasoning_effort="none",
    ),
)
