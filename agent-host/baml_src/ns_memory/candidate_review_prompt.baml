function SelectCandidateMemories(
    purpose: string,
    candidates: CandidateMemoryEntry[],
    stored_memories: StoredCandidateMemory[],
) -> CandidateMemoryReviewDecision {
    client: CandidateMemoryReviewModel
    prompt: #"
        {{ _.role("system") }}

        Select guidance memories that will be useful for future decisions about {{ purpose }}.

        Favor guidance that is durable, supported by the observed interaction, distinct from stored guidance, and useful beyond the immediate request.

        Build a compact selection where every kept candidate contributes a distinct insight.

        {{ _.role("user") }}

        Stored guidance:
        {% for memory in stored_memories %}
        - {{ memory.title }}
          Tags: {{ memory.tags }}
          created_at: {{ memory.created_at }}
          updated_at: {{ memory.updated_at }}
          read_at: {{ memory.read_at }}
          {{ memory.description }}
        {% endfor %}

        New candidates:
        {% for candidate in candidates %}
        - id: {{ candidate.id }}
          title: {{ candidate.title }}
          description: {{ candidate.description }}
        {% endfor %}

        Return the ids of the candidates worth keeping.

        {{ ctx.output_format }}
    "#
}
