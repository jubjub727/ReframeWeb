testset "task conversation" {
    test "keeps resolved history and this task reply" {
        let conversation = root.turn_context.ConversationHistory {
            id: "conversation",
            name: "Current conversation",
            created_at: "created",
            updated_at: "updated",
            read_at: "read",
            messages: [
                root.turn_context.ConversationHistoryMessage {
                    created_at: "resolved-human",
                    updated_at: "updated",
                    read_at: "read",
                    role: "human",
                    content: "resolved request",
                },
                root.turn_context.ConversationHistoryMessage {
                    created_at: "this-human",
                    updated_at: "updated",
                    read_at: "read",
                    role: "human",
                    content: "this request",
                },
                root.turn_context.ConversationHistoryMessage {
                    created_at: "other-human",
                    updated_at: "updated",
                    read_at: "read",
                    role: "human",
                    content: "other active request",
                },
                root.turn_context.ConversationHistoryMessage {
                    created_at: "agent",
                    updated_at: "updated",
                    read_at: "read",
                    role: "agent_reply",
                    content: "resolved answer",
                },
                root.turn_context.ConversationHistoryMessage {
                    created_at: "validation",
                    updated_at: "updated",
                    read_at: "read",
                    role: "validation_reply",
                    content: "Previous retry guidance",
                },
            ],
        };
        let scoped = TaskConversation(
            conversation,
            VoiceTaskConversationScope {
                current_human_reply_created_at: "this-human",
                active_human_reply_created_at: ["this-human", "other-human"],
            },
        );
        assert.not_null(scoped);
        if let task_conversation: root.turn_context.ConversationHistory = scoped {
            assert.equal(task_conversation.messages.length(), 4);
            assert.equal(task_conversation.messages.at(0)?.content, "resolved request");
            assert.equal(task_conversation.messages.at(1)?.content, "this request");
            assert.equal(task_conversation.messages.at(2)?.content, "resolved answer");
            assert.equal(task_conversation.messages.at(3)?.role, "validation_reply");
            assert.equal(task_conversation.messages.at(3)?.content, "Previous retry guidance")
        }
    }

    test "preserves missing conversation" {
        assert
            .equal(
                TaskConversation(
                    null,
                    VoiceTaskConversationScope {
                        current_human_reply_created_at: null,
                        active_human_reply_created_at: [],
                    },
                ),
                null,
            )
    }
}
