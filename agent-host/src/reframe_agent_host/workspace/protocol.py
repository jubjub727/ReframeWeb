from __future__ import annotations

from typing import Any

from pydantic import BaseModel


MAX_FRAME_BYTES = 16 * 1024 * 1024


class WorkspaceProtocolError(BaseModel):
    code: str
    operation: str
    workspace_id: str | None = None
    message: str


class WorkspaceResponse(BaseModel):
    request_id: str
    ok: bool
    result: Any | None = None
    error: WorkspaceProtocolError | None = None


def request_payload(
    operation: str,
    request_id: str,
    *,
    idempotency_key: str | None,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "request_id": request_id,
        "operation": operation,
        **arguments,
    }
    if idempotency_key is not None:
        payload["idempotency_key"] = idempotency_key
    return payload
