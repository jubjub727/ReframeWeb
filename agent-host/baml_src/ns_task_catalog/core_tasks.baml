function CoreTasks() -> CoreTaskDefinition[] {
    [
        CoreTaskDefinition {
            name: "Explain request cannot be handled",
            description: "Use when the most useful response is a clear limitation, boundary, or next-best path.",
            input: "The user's request.",
            output: "The user received a clear explanation that the request cannot be handled, including the relevant limitation or boundary and a useful next step when available.",
            prompt: `
                Give the human a clear, brief explanation of the relevant limitation or boundary. Offer the most useful next step when one is available.

                Allowed return items:
                - agent_reply with payload {"text": "..."} for the message the user should hear.
                - agent_thought with payload {"text": "..."} for useful private context that belongs in the conversation.
                - session_memory with payload {"title": "...", "description": "..."} when the request reveals useful context for this session.
                - user_preference with payload {"title": "...", "description": "..."} when the request reveals a durable user preference or user-relevant information.
            `,
            tags: ["limitation", "boundary"],
            model_id: "glm-5.1",
            reasoning_effort: "none",
        },
        CoreTaskDefinition {
            name: "Request more information from the user",
            description: "Use when a useful next step depends on one specific piece of input from the human.",
            input: "The user's request.",
            output: "The user was asked for the specific missing information needed to continue the task.",
            prompt: `
                Ask the human for the information needed to continue. Ask for the smallest useful piece of information, and make the next answer easy to provide.

                Allowed return items:
                - agent_reply with payload {"text": "..."} for the question the user should hear.
                - agent_thought with payload {"text": "..."} for useful private context that belongs in the conversation.
                - session_memory with payload {"title": "...", "description": "..."} when the request reveals useful context for this session.
                - user_preference with payload {"title": "...", "description": "..."} when the request reveals a durable user preference or user-relevant information.
            `,
            tags: ["needs-information"],
            model_id: "glm-5.1",
            reasoning_effort: "none",
        },
        CoreTaskDefinition {
            name: "Turn conversation mode off",
            description: "Use when the user asks the assistant to stop staying in continuous conversation or to wait until they address it again.",
            input: "The user's request to end continuous conversation.",
            output: "Continuous conversation mode was turned off.",
            prompt: `
                End continuous conversation so the assistant goes quiet until the user addresses it again. Give a short confirmation when that would feel natural.

                Allowed return items:
                - conversation_mode_off with empty payload {} to end continuous conversation.
                - agent_reply with payload {"text": "..."} for a brief confirmation the user should hear.
                - agent_thought with payload {"text": "..."} for useful private context that belongs in the conversation.
            `,
            tags: ["conversation-mode", "conversation-off"],
            model_id: "kimi-k2.6",
            reasoning_effort: "none",
        },
        CoreTaskDefinition {
            name: "Thinking",
            description: "Use when the useful work is private thinking, recording context, or updating memory without speaking to the user.",
            input: "The user's request or conversational context.",
            output: "Useful non-spoken context was preserved as an internal thought, session memory, or user preference.",
            prompt: `
                Think privately about the supplied request or context. Use this task only for useful non-spoken work: preserving internal context, noting a relevant thought, or recording memory. If there is nothing useful to record, return an empty returns array.

                Allowed return items:
                - agent_thought with payload {"text": "..."} for useful private context that belongs in the conversation.
                - session_memory with payload {"title": "...", "description": "..."} when the exchange reveals useful context for this session.
                - user_preference with payload {"title": "...", "description": "..."} when the exchange reveals a durable user preference or user-relevant information.
            `,
            tags: ["thinking", "silent", "memory"],
            model_id: "glm-5.1",
            reasoning_effort: "none",
        },
        CoreTaskDefinition {
            name: "Do nothing",
            description: "Use when the correct response is to take no action, say nothing, and record nothing.",
            input: "The user's request or conversational context.",
            output: "",
            prompt: "Do nothing. Return an empty returns array.\n",
            tags: ["nothing", "silent"],
            model_id: "magic:do-nothing",
            reasoning_effort: null,
        },
        CoreTaskDefinition {
            name: "Greeting",
            description: "Use when the user's message is a simple greeting, check-in, or conversational opener.",
            input: "The user's greeting or conversational opener.",
            output: "The user received a brief, natural greeting or conversational acknowledgement.",
            prompt: `
                Respond naturally to the human's greeting or conversational opener. Keep it brief, warm, and style-matched. Do not turn a simple greeting into a broad follow-up unless that would clearly be useful.

                Allowed return items only:
                - agent_reply with payload {"text": "..."} for the greeting the user should hear.
                Use only the item type listed above.
            `,
            tags: ["greeting", "reply"],
            model_id: "glm-5.1",
            reasoning_effort: "none",
        },
        CoreTaskDefinition {
            name: "Reply to user",
            description: "Use when the user wants a conversational answer and the useful result is simply something said back to them. Do not reply simply for the sake of replying.",
            input: "The user's message.",
            output: "The user received a useful spoken reply that answered or responded to their message.",
            prompt: `
                Answer the human directly using the supplied request. Keep the reply concise, conversational, and useful.
                Do not return agent_reply just to acknowledge that a request was heard. Only return agent_reply when there is a useful spoken message for the human. If no spoken reply is useful, return only the relevant non-spoken items, or an empty returns array when there is nothing useful to record. Only reply when it's appropriate.

                Allowed return items:
                - agent_reply with payload {"text": "..."} for the message the user should hear.
                - agent_thought with payload {"text": "..."} for useful private context that belongs in the conversation.
                - session_memory with payload {"title": "...", "description": "..."} when the exchange reveals useful context for this session.
                - user_preference with payload {"title": "...", "description": "..."} when the exchange reveals a durable user preference or user-relevant information.
            `,
            tags: ["reply"],
            model_id: "glm-5.1",
            reasoning_effort: "none",
        },
    ]
}

testset "core task catalog" {
    test "has the complete ordered catalog" {
        let tasks = CoreTasks();
        assert.equal(tasks.length(), 7);
        assert.equal(tasks[0].name, "Explain request cannot be handled");
        assert.equal(tasks[1].name, "Request more information from the user");
        assert.equal(tasks[2].name, "Turn conversation mode off");
        assert.equal(tasks[3].name, "Thinking");
        assert.equal(tasks[4].name, "Do nothing");
        assert.equal(tasks[5].name, "Greeting");
        assert.equal(tasks[6].name, "Reply to user")
    }

    test "keeps provider intent with each task" {
        let tasks = CoreTasks();
        assert.equal(tasks[0].model_id, "glm-5.1");
        assert.equal(tasks[0].reasoning_effort, "none");
        assert.equal(tasks[1].model_id, "glm-5.1");
        assert.equal(tasks[1].reasoning_effort, "none");
        assert.equal(tasks[2].model_id, "kimi-k2.6");
        assert.equal(tasks[2].reasoning_effort, "none");
        assert.equal(tasks[3].model_id, "glm-5.1");
        assert.equal(tasks[3].reasoning_effort, "none");
        assert.equal(tasks[4].model_id, "magic:do-nothing");
        assert.equal(tasks[4].reasoning_effort, null);
        assert.equal(tasks[5].model_id, "glm-5.1");
        assert.equal(tasks[5].reasoning_effort, "none");
        assert.equal(tasks[6].model_id, "glm-5.1");
        assert.equal(tasks[6].reasoning_effort, "none")
    }

    test "describes only the user supplied input" {
        let tasks = CoreTasks();
        assert.equal(tasks[0].input, "The user's request.");
        assert.equal(tasks[1].input, "The user's request.");
        assert.equal(tasks[2].input, "The user's request to end continuous conversation.");
        assert.equal(tasks[3].input, "The user's request or conversational context.");
        assert.equal(tasks[4].input, "The user's request or conversational context.");
        assert.equal(tasks[5].input, "The user's greeting or conversational opener.");
        assert.equal(tasks[6].input, "The user's message.")
    }

    test "owns each task return contract" {
        let tasks = CoreTasks();
        assert.contains(tasks[2].prompt, "conversation_mode_off with empty payload {}");
        assert.contains(tasks[3].prompt, "agent_thought");
        assert.contains(tasks[3].prompt, "session_memory");
        assert.contains(tasks[3].prompt, "user_preference");
        assert.contains(tasks[4].prompt, "Return an empty returns array");
        assert.contains(tasks[5].prompt, "brief, warm, and style-matched");
        assert.contains(tasks[6].prompt, "Do not return agent_reply just to acknowledge");
        assert.contains(tasks[6].prompt, "Only reply when it's appropriate.")
    }

    test "keeps task tags and outcomes intentional" {
        let tasks = CoreTasks();
        assert.equal(tasks[2].tags, ["conversation-mode", "conversation-off"]);
        assert.equal(tasks[3].tags, ["thinking", "silent", "memory"]);
        assert.equal(tasks[4].tags, ["nothing", "silent"]);
        assert.equal(tasks[5].tags, ["greeting", "reply"]);
        assert.equal(tasks[6].tags, ["reply"]);
        assert.equal(tasks[4].output, "");
        assert.equal(tasks[2].output, "Continuous conversation mode was turned off.");
        assert.contains(tasks[6].output, "useful spoken reply")
    }
}
