from __future__ import annotations

import json
from typing import Any

import baml_sdk as baml
import baml_sdk as types
from baml_sdk import baml as baml_std
from reframe_agent_host.agent_flow.baml_clients import BamlClient, client_kwargs


def opencode_response_compat_required(client_name: str) -> bool:
    return client_name.startswith("OpenCodeGoModelKimiK26")


async def execute_task_via_opencode_response_compat(
    *,
    full_task_prompt: str,
    client: BamlClient | str | None = None,
) -> types.TaskExecutionResult:
    request = await baml.ExecuteTask__build_request_async(
        full_task_prompt=full_task_prompt,
        **client_kwargs(client),
    )
    response = await baml_std.http.send_async(
        baml_std.http.Request(
            method=request.method,
            url=request.url,
            headers=dict(request.headers),
            body=request.body,
        )
    )
    text = await response.text_async()
    if not await response.ok_async():
        msg = f"OpenCode task execution failed with HTTP {response.status_code}: {text}"
        raise RuntimeError(msg)

    return await baml.ExecuteTask__parse_async(
        json=assistant_content_from_chat_response(text),
        **client_kwargs(client),
    )


def assistant_content_from_chat_response(response_text: str) -> str:
    data = json.loads(response_text)
    choices = _list_field(data, "choices")
    choice = _mapping(choices[0], "choices[0]")
    message = _mapping(choice.get("message"), "choices[0].message")
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(_text_part(part) for part in content)

    msg = "OpenCode response did not include assistant message content"
    raise ValueError(msg)


def _text_part(part: Any) -> str:
    if isinstance(part, str):
        return part
    mapping = _mapping(part, "message.content[]")
    if mapping.get("type") == "text" and isinstance(mapping.get("text"), str):
        return mapping["text"]
    return ""


def _list_field(mapping: Any, field: str) -> list[Any]:
    value = _mapping(mapping, "response").get(field)
    if isinstance(value, list) and value:
        return value
    msg = f"OpenCode response field is missing or empty: {field}"
    raise ValueError(msg)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    msg = f"OpenCode response field is not an object: {name}"
    raise ValueError(msg)
