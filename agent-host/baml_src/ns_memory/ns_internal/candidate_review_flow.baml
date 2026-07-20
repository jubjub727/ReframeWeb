function CandidateMemoryReviewInputs(
    groups: root.memory.CandidateMemoryGroups,
    context: root.memory.CandidateMemoryReviewContext,
) -> CandidateMemoryReviewInput[] {
    let inputs: CandidateMemoryReviewInput[] = [];
    AddCandidateMemoryReviewInput(inputs, root.memory.CandidateMemoryLayer.TASK_CHOICE, groups.task_choice, context.task_choice);
    AddCandidateMemoryReviewInput(
        inputs,
        root.memory.CandidateMemoryLayer.CONVERSATION_EVALUATION,
        groups.conversation_evaluation,
        context.conversation_evaluation,
    );
    AddCandidateMemoryReviewInput(
        inputs,
        root.memory.CandidateMemoryLayer.SEARCH_DEPTH,
        groups.search_depth,
        context.search_depth,
    );
    AddCandidateMemoryReviewInput(inputs, root.memory.CandidateMemoryLayer.RELEVANCE, groups.relevance, context.relevance);
    AddCandidateMemoryReviewInput(inputs, root.memory.CandidateMemoryLayer.TASK_PROMPT, groups.task_prompt, context.task_prompt);
    inputs
}

function AddCandidateMemoryReviewInput(
    inputs: CandidateMemoryReviewInput[],
    layer: root.memory.CandidateMemoryLayer,
    candidates: root.memory.CandidateMemoryEntry[],
    stored_memories: root.memory.StoredCandidateMemory[],
) -> void {
    if (candidates.length() > 0) {
        inputs
            .push(
                CandidateMemoryReviewInput {
                    layer: layer,
                    purpose: CandidateMemoryPurpose(layer),
                    candidates: candidates,
                    stored_memories: stored_memories,
                },
            );
    }
}

function KeptCandidateMemories(
    candidates: root.memory.CandidateMemoryEntry[],
    decision: root.memory.CandidateMemoryReviewDecision,
) -> root.memory.CandidateMemoryEntry[] {
    candidates
        .filter(
            (candidate) -> {
                decision.kept_candidate_ids.includes(candidate.id)
            },
        )
}

function CandidateMemoryWriteBatchFromReviews(
    reviews: CandidateMemoryReview[],
) -> root.memory.CandidateMemoryWriteBatch {
    let batch = EmptyCandidateMemoryWriteBatch();
    for (let review in reviews) {
        match (review.layer) {
            root.memory.CandidateMemoryLayer.TASK_CHOICE => {
                batch.task_choice = review.kept_candidates;
                null
            },
            root.memory.CandidateMemoryLayer.CONVERSATION_EVALUATION => {
                batch.conversation_evaluation = review.kept_candidates;
                null
            },
            root.memory.CandidateMemoryLayer.SEARCH_DEPTH => {
                batch.search_depth = review.kept_candidates;
                null
            },
            root.memory.CandidateMemoryLayer.RELEVANCE => {
                batch.relevance = review.kept_candidates;
                null
            },
            root.memory.CandidateMemoryLayer.TASK_PROMPT => {
                batch.task_prompt = review.kept_candidates;
                null
            },
        }
    }
    batch
}

function CandidateMemoryPurpose(layer: root.memory.CandidateMemoryLayer) -> string {
    match (layer) {
        root.memory.CandidateMemoryLayer.TASK_CHOICE => "choosing the right task for a user request",
        root.memory.CandidateMemoryLayer.CONVERSATION_EVALUATION => {
            "planning which memories will help with a user request and selected task"
        },
        root.memory.CandidateMemoryLayer.SEARCH_DEPTH => {
            "choosing useful time ranges for memory search"
        },
        root.memory.CandidateMemoryLayer.RELEVANCE => {
            "selecting retrieved memories that help the selected task"
        },
        root.memory.CandidateMemoryLayer.TASK_PROMPT => {
            "composing clear task input from the request and selected context"
        },
    }
}
