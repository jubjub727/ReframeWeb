from __future__ import annotations

from http.server import ThreadingHTTPServer

from reframe_agent_host.memory_browser.handler import MemoryBrowserHandler


def serve_memory_browser(host: str, port: int) -> int:
    server = ThreadingHTTPServer((host, port), MemoryBrowserHandler)
    url = f"http://{host}:{server.server_port}"
    print(f"memory browser available at {url}")
    print("press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping memory browser")
    finally:
        server.server_close()
    return 0
