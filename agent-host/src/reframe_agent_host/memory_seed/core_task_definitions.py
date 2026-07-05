from __future__ import annotations

from dataclasses import dataclass

from reframe_memory import Provider, Task


CORE_TASK_PROVIDER = Provider(
    name="Core repair task provider",
    description="Built-in tasks for handling requests that cannot continue directly.",
    baml_surface="CoreRepairTask",
)
CORE_TASK_TAGS = ("core", "repair")
CORE_TASK_MODEL_ID = "deepseek-v4-flash"
CORE_TASK_REASONING_EFFORT = "xhigh"

CORE_TASK_RETURN_OPTIONS = (
    "This task may respond with named items. Use agent_reply with payload "
    "{\"text\": \"...\"} for text that should be shown and spoken to the user; "
    "agent_thought with payload {\"text\": \"...\"} for private context that "
    "should be saved to the conversation without being spoken; session_memory "
    "with payload {\"title\": \"...\", \"description\": \"...\"} for useful "
    "context that only belongs to the current session; user_preference with "
    "payload {\"title\": \"...\", \"description\": \"...\"} for durable "
    "preferences that should apply globally in future sessions. Other "
    "included guidance may describe additional named items."
)


@dataclass(frozen=True)
class CoreTaskDefinition:
    name: str
    description: str
    input: str
    output: str
    prompt: str
    tags: tuple[str, ...]

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
            "Use when the requested behavior is impossible, unsupported, or "
            "outside the system's current capabilities."
        ),
        input=(
            "The user's request as it relates to the behavior they want "
            "performed."
        ),
        output=(
            "Return named items that explain why the requested behavior "
            "cannot be handled and preserve useful context."
        ),
        prompt=(
            CORE_TASK_RETURN_OPTIONS
            + " "
            "Identify why the requested behavior cannot be handled with the "
            "system's current capabilities, then explain the limitation to the "
            "human clearly and briefly. Do not invent capabilities or pretend "
            "the request can be completed. Keep the reply direct, useful, and "
            "conversational. Return agent_reply when the user should hear the "
            "limitation. Return agent_thought for useful private context that "
            "belongs in the conversation but should not be spoken aloud. Return "
            "session_memory or user_preference only when the request reveals "
            "context worth saving."
        ),
        tags=CORE_TASK_TAGS + ("not-possible",),
    ),
    CoreTaskDefinition(
        name="Request more information from the user",
        description=(
            "Use when the request needs input from the human before it can be "
            "handled well."
        ),
        input=(
            "The user's request as it relates to the behavior they want "
            "performed."
        ),
        output=(
            "Return named items that ask for the information needed to "
            "continue and preserve useful context."
        ),
        prompt=(
            CORE_TASK_RETURN_OPTIONS
            + " "
            "Identify what is needed from the human, then ask for it. Ask only "
            "for what matters. Keep the reply concise and make the next answer "
            "easy to provide. Return agent_reply for the question the user "
            "should hear. Return agent_thought for useful private context that "
            "belongs in the conversation but should not be spoken aloud. Return "
            "session_memory or user_preference only when the request reveals "
            "context worth saving."
        ),
        tags=CORE_TASK_TAGS + ("needs-information",),
    ),
)
