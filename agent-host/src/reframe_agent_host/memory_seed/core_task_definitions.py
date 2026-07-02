from __future__ import annotations

from dataclasses import dataclass

from reframe_memory import Provider, Task


CORE_TASK_PROVIDER = Provider(
    name="Core repair task provider",
    description="Built-in tasks for handling requests that cannot continue directly.",
    baml_surface="CoreRepairTask",
)
CORE_TASK_TAGS = ("core", "repair")


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
            "Return a human_reply that explains why the requested behavior "
            "cannot be handled. Include an agent_thought when useful private "
            "context should be added to the conversation without being spoken "
            "to the human. Include a candidate_memory when there is a useful "
            "observation to preserve."
        ),
        prompt=(
            "Identify why the requested behavior cannot be handled with the "
            "system's current capabilities, then explain the limitation to the "
            "human clearly and briefly. Do not invent capabilities or pretend "
            "the request can be completed. Keep the reply direct, useful, and "
            "conversational. Include an agent_thought for useful private context "
            "that belongs in the conversation but should not be spoken aloud. "
            "Include a candidate_memory when there is a useful observation to "
            "preserve."
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
            "Return a human_reply that asks for the information needed to "
            "continue. Include an agent_thought when useful private context "
            "should be added to the conversation without being spoken to the "
            "human. Include a candidate_memory when there is a useful "
            "observation to preserve."
        ),
        prompt=(
            "Identify what is needed from the human, then ask for it. Ask only "
            "for what matters. Keep the reply concise and make the next answer "
            "easy to provide. Include an agent_thought for useful private "
            "context that belongs in the conversation but should not be spoken "
            "aloud. Include a candidate_memory when there is a useful observation "
            "to preserve."
        ),
        tags=CORE_TASK_TAGS + ("needs-information",),
    ),
)
