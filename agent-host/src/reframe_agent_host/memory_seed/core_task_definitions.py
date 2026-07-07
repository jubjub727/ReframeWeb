from __future__ import annotations

from dataclasses import dataclass

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
            "user preference."
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
            "user preference."
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
        name="Reply to user",
        description=(
            "Use when the user wants a conversational answer and the useful "
            "result is simply something said back to them."
        ),
        input="The user's message.",
        output="Named return items that reply to the user.",
        prompt=(
            "Answer the human directly using the supplied request. Keep the "
            "reply concise, conversational, and useful.\n\n"
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
            "user preference."
        ),
        tags=("reply",),
        model_id="glm-5.1",
        reasoning_effort="none",
    ),
)
