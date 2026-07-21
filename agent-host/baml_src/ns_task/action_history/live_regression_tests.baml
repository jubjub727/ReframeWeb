// This test calls the configured action-history model. Run it explicitly when
// validating summary behavior; it is not a token-free parser test.

test "action summary preserves a formatted payload as one value" {
    let summary = SummariseActionHistory(
        `
            - Action:
                name: agent_reply
                input:
                  {"text": "476,837,158,203,128"}
                output:
                  {"status": "ok", "text": "476,837,158,203,128"}
        `,
    );
    assert.contains(summary, "476,837,158,203,128");
    assert.is_true(!summary.to_lower_case().includes("five numbers"))
}
