from __future__ import annotations

import json

from reframe_agent_host.agent_flow.opencode_response_compat import (
    assistant_content_from_chat_response,
    opencode_response_compat_required,
)


def test_assistant_content_ignores_reasoning_content() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '{"returns":[]}',
                    "reasoning_content": "internal reasoning",
                }
            }
        ]
    }

    assert assistant_content_from_chat_response(json.dumps(response)) == '{"returns":[]}'


def test_assistant_content_accepts_text_parts() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": '{"returns":'},
                        {"type": "text", "text": "[]}"},
                    ],
                }
            }
        ]
    }

    assert assistant_content_from_chat_response(json.dumps(response)) == '{"returns":[]}'


def test_response_compat_is_scoped_to_kimi_26_opencode_clients() -> None:
    assert opencode_response_compat_required("OpenCodeGoModelKimiK26") is True
    assert opencode_response_compat_required("OpenCodeGoModelKimiK26ReasoningNone")
    assert opencode_response_compat_required("OpenCodeGoModelKimiK25") is False
