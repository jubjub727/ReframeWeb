test "opencode glm 5.1 no reasoning smoke" {
    let run_smoke = baml.env.get("RUN_OPENCODE_GLM51_TASK_EXECUTION_SMOKE") ?? "";

    if (run_smoke != "1") {
        assert.equal(run_smoke == "1", false)
    } else {
        let prompt = `
            Task:
            Return no response items.

            Output:
            A TaskExecutionResult with an empty returns array.
        `;
        let request = PerformTask$build_request(prompt);
        let body = baml.json.parse(request.body);

        assert.equal(baml.json.to<string>(baml.json.field(body, "model")), "glm-5.1");
        assert.equal(baml.json.to<string>(baml.json.field(body, "reasoning_effort")), "none");

        let result = PerformTask(prompt);
        assert.equal(result.returns.length(), 0)
    }
}

test "opencode reply task uses glm 5.1 no reasoning smoke" {
    let run_smoke = baml.env.get("RUN_OPENCODE_GLM51_TASK_EXECUTION_SMOKE") ?? "";

    if (run_smoke != "1") {
        assert.equal(run_smoke == "1", false)
    } else {
        let prompt = `
            Task:
            Answer the human directly using the supplied request. Keep the reply
            concise, conversational, and useful.

            Allowed return items:
            - agent_reply with payload {"text": "..."} for the message the user
              should hear.
            - agent_thought with payload {"text": "..."} for useful private context.

            Input:
            Say hello in one short sentence.
        `;
        let request = PerformTask$build_request(prompt, client = OpenCodeGoModelGlm51ReasoningNone);
        let body = baml.json.parse(request.body);

        assert.equal(baml.json.to<string>(baml.json.field(body, "model")), "glm-5.1");
        assert.equal(baml.json.to<string>(baml.json.field(body, "reasoning_effort")), "none");

        let result = PerformTask(prompt, client = OpenCodeGoModelGlm51ReasoningNone);
        assert
            .is_true(
                result
                    .returns
                    .some(
                        (item) -> {
                            item.name == "agent_reply" && (item.payload?.get("text") ?? "") != ""
                        },
                    ),
            )
    }
}
