testset "candidate memory review" {
    test "candidates accumulate across task cycles by prompt layer" {
        let groups = root.memory.EmptyCandidateMemoryGroups();
        root.memory
            .AddCandidateMemory(
                groups,
                root.memory.CandidateMemoryLayer.TASK_CHOICE,
                root.memory.CandidateMemory {
                    title: "First route",
                    description: "First observation",
                },
            );
        root.memory
            .AddCandidateMemory(
                groups,
                root.memory.CandidateMemoryLayer.TASK_CHOICE,
                root.memory.CandidateMemory {
                    title: "Second route",
                    description: "Second observation",
                },
            );
        root.memory
            .AddCandidateMemory(
                groups,
                root.memory.CandidateMemoryLayer.RELEVANCE,
                root.memory.CandidateMemory {
                    title: "Relevant context",
                    description: "Third observation",
                },
            );
        assert.equal(CandidateMemoryCount(groups), 3);
        assert.equal(groups.task_choice.length(), 2);
        assert.equal(groups.relevance.length(), 1);
        assert.equal(groups.task_choice[0].id, "task_choice-1");
        assert.equal(groups.task_choice[1].id, "task_choice-2")
    }

    test "empty candidates take the review fast path" {
        let inputs = CandidateMemoryReviewInputs(root.memory.EmptyCandidateMemoryGroups(), EmptyCandidateMemoryReviewContext());
        assert.equal(inputs.length(), 0)
    }

    test "one focused input is built for each populated layer" {
        let groups = root.memory.EmptyCandidateMemoryGroups();
        root.memory
            .AddCandidateMemory(
                groups,
                root.memory.CandidateMemoryLayer.SEARCH_DEPTH,
                root.memory.CandidateMemory {
                    title: "Search range",
                    description: "A durable range observation",
                },
            );
        root.memory
            .AddCandidateMemory(
                groups,
                root.memory.CandidateMemoryLayer.TASK_PROMPT,
                root.memory.CandidateMemory {
                    title: "Handoff",
                    description: "A durable handoff observation",
                },
            );
        let inputs = CandidateMemoryReviewInputs(groups, EmptyCandidateMemoryReviewContext());
        assert.equal(inputs.length(), 2);
        assert.equal(inputs[0].layer, root.memory.CandidateMemoryLayer.SEARCH_DEPTH);
        assert.equal(inputs[1].layer, root.memory.CandidateMemoryLayer.TASK_PROMPT)
    }

    test "selected ids resolve known candidates" {
        let candidates = [
            root.memory.CandidateMemoryEntry { id: "a", title: "A", description: "First" },
            root.memory.CandidateMemoryEntry { id: "b", title: "B", description: "Second" },
        ];
        let kept = KeptCandidateMemories(candidates, root.memory.CandidateMemoryReviewDecision { kept_candidate_ids: ["b"] });
        assert.equal(kept.length(), 1);
        assert.equal(kept[0].id, "b")
    }

    test "reviewed candidates remain grouped for append only writeback" {
        let candidate = root.memory.CandidateMemoryEntry {
            id: "task_prompt-1",
            title: "Task prompt guidance",
            description: "Useful guidance",
        };
        let batch = CandidateMemoryWriteBatchFromReviews(
            [
                CandidateMemoryReview {
                    layer: root.memory.CandidateMemoryLayer.TASK_PROMPT,
                    candidates: [candidate],
                    kept_candidates: [candidate],
                },
            ],
        );
        assert.equal(batch.task_prompt.length(), 1);
        assert.equal(batch.task_choice.length(), 0);
        assert.is_true(HasSelectedCandidates(batch))
    }

    test "review parser returns candidate ids" {
        let decision = root.memory.SelectCandidateMemories$parse(#"{ "kept_candidate_ids": ["task_choice-1"] }"#);
        assert.equal(decision.kept_candidate_ids, ["task_choice-1"])
    }
}

function EmptyCandidateMemoryReviewContext() -> root.memory.CandidateMemoryReviewContext {
    root.memory.CandidateMemoryReviewContext {
        task_choice: [],
        conversation_evaluation: [],
        search_depth: [],
        relevance: [],
        task_prompt: [],
    }
}
