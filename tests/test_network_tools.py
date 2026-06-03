from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from repopilot.config import AppConfig, NetworkSettings
from repopilot.tools.network import FetchUrlInput, web_fetch_url


class TextHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = "hello from docs"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format: str, *args) -> None:
        return


def test_web_fetch_url_can_read_text_when_enabled() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), TextHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = AppConfig(network=NetworkSettings(deny_private_hosts=False))

    try:
        result = web_fetch_url(FetchUrlInput(url=f"http://127.0.0.1:{server.server_port}/docs"), config)
    finally:
        server.shutdown()
        server.server_close()

    assert "hello from docs" in result
    assert "HTTP 状态" in result


def test_web_fetch_url_blocks_private_hosts_by_default() -> None:
    result = web_fetch_url(FetchUrlInput(url="http://127.0.0.1:8765/"), AppConfig())

    assert "拒绝访问" in result


def test_web_fetch_url_honors_network_disable() -> None:
    config = AppConfig(network=NetworkSettings(allow_http_fetch=False))

    result = web_fetch_url(FetchUrlInput(url="https://example.com"), config)

    assert "allow_http_fetch=false" in result
