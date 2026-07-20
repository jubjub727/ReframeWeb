function ReviewMemories(
    candidates: root.memory.CandidateMemoryGroups,
    context: root.memory.CandidateMemoryReviewContext,
) -> root.memory.CandidateMemoryWriteBatch {
    let inputs = root.memory.internal.CandidateMemoryReviewInputs(candidates, context);
    let reviews = await baml.future.all(
        inputs
            .map(
                (input) -> {
                    spawn {
                        let decision = root.memory.SelectCandidateMemories(
                            input.purpose,
                            input.candidates,
                            input.stored_memories,
                        );
                        root.memory.internal.CandidateMemoryReview {
                            layer: input.layer,
                            candidates: input.candidates,
                            kept_candidates: root.memory.internal.KeptCandidateMemories(input.candidates, decision),
                        }
                    }
                },
            ),
    );
    root.memory.internal.CandidateMemoryWriteBatchFromReviews(reviews)
}
