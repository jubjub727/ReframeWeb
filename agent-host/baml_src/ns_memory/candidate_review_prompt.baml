function SelectCandidateMemories(
    purpose: string,
    candidates: CandidateMemoryEntry[],
    stored_memories: StoredCandidateMemory[],
) -> CandidateMemoryReviewDecision {
    client: CandidateMemoryReviewModel
    prompt: `
        ${role("system")}

        Select guidance memories that will be useful for future decisions about ${purpose}.

        Favor guidance that is durable, supported by the observed interaction, distinct from stored guidance, and useful beyond the immediate request.

        Build a compact selection where every kept candidate contributes a distinct insight.

        Keep a candidate only when the observation itself describes a reusable
        lesson about the decision behavior named by the stated purpose.

        Reject candidates that store, paraphrase, consolidate, infer, or promote
        user facts, user preferences, formatting preferences, request content,
        task instructions, task results, or the contents of this layer's inputs.
        Their usefulness elsewhere does not make them guidance for this purpose.
        Do not rescue or reinterpret a misplaced candidate. If it could be read
        as something to remember about the user or task instead of the decision
        layer, reject it.

        ${role("user")}

        Stored guidance:
        ${stored_memories.map((memory) -> {
            `- ${memory.title}
          Tags: ${memory.tags}
          created_at: ${memory.created_at}
          updated_at: ${memory.updated_at}
          read_at: ${memory.read_at}
          ${memory.description}`
        }).join("\n")}

        New candidates:
        ${candidates.map((candidate) -> {
            `- id: ${candidate.id}
          title: ${candidate.title}
          description: ${candidate.description}`
        }).join("\n")}

        Return the ids of the candidates worth keeping.

        ${ctx.output_format}
    `
}
