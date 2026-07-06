from __future__ import annotations

from reframe_agent_host.memory_browser.server import serve_memory_browser


def run_memory_browser(args) -> int:
    return serve_memory_browser(host=args.host, port=args.port)
