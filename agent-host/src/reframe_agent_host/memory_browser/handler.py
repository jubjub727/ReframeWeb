from __future__ import annotations

import asyncio
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from reframe_agent_host.memory_browser import records
from reframe_agent_host.memory_browser.catalog import TABLES, VIEWS


STATIC_DIR = Path(__file__).with_name("static")


class MemoryBrowserHandler(SimpleHTTPRequestHandler):
    server_version = "ReframeMemoryBrowser/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api_get(parsed.path, parse_qs(parsed.query))
            return
        self._serve_static(parsed.path)

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/node":
            self._send_error(HTTPStatus.NOT_FOUND, "unknown endpoint")
            return
        try:
            body = self._read_json_body()
            result = asyncio.run(
                records.update_node(
                    str(body.get("id") or ""),
                    body.get("tags"),
                    body.get("content"),
                )
            )
            self._send_json(result)
        except Exception as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/node":
            self._send_error(HTTPStatus.NOT_FOUND, "unknown endpoint")
            return
        try:
            query = parse_qs(parsed.query)
            result = asyncio.run(records.delete_node(_query_value(query, "id", "")))
            self._send_json(result)
        except LookupError as exc:
            self._send_error(HTTPStatus.NOT_FOUND, str(exc))
        except Exception as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def log_message(self, format: str, *args) -> None:
        return

    def _handle_api_get(self, path: str, query: dict[str, list[str]]) -> None:
        try:
            if path == "/api/config":
                self._send_json(
                    {
                        "views": [view.__dict__ for view in VIEWS],
                        "tables": TABLES,
                    }
                )
                return
            if path == "/api/overview":
                self._send_json(asyncio.run(records.overview()))
                return
            if path == "/api/nodes":
                self._send_json(
                    asyncio.run(
                        records.list_nodes(
                            _query_value(query, "view", "sessions"),
                            _query_value(query, "q", ""),
                        )
                    )
                )
                return
            if path == "/api/node":
                self._send_json(
                    asyncio.run(records.node_detail(_query_value(query, "id", "")))
                )
                return
            if path == "/api/table":
                self._send_json(
                    asyncio.run(
                        records.table_rows(
                            _query_value(query, "name", "memory_node"),
                        )
                    )
                )
                return
            self._send_error(HTTPStatus.NOT_FOUND, "unknown endpoint")
        except LookupError as exc:
            self._send_error(HTTPStatus.NOT_FOUND, str(exc))
        except Exception as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def _serve_static(self, path: str) -> None:
        target = "index.html" if path in ("", "/") else path.lstrip("/")
        full_path = (STATIC_DIR / target).resolve()
        if STATIC_DIR.resolve() not in full_path.parents and full_path != STATIC_DIR:
            self._send_error(HTTPStatus.NOT_FOUND, "not found")
            return
        if not full_path.is_file():
            self._send_error(HTTPStatus.NOT_FOUND, "not found")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", _content_type(full_path))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(full_path.read_bytes())

    def _read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        body = json.loads(raw or "{}")
        if not isinstance(body, dict):
            raise ValueError("request body must be a JSON object")
        return body

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status)


def _query_value(query: dict[str, list[str]], key: str, default: str) -> str:
    values = query.get(key)
    return values[0] if values else default


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".css":
        return "text/css; charset=utf-8"
    if suffix == ".js":
        return "text/javascript; charset=utf-8"
    return "text/html; charset=utf-8"
