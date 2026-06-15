"""A small HTTP API so the watch (and other clients) can talk to Sunny.

One endpoint that matters:
    POST /chat   {"message": "..."}   -> {"reply": "..."}
plus GET /health for liveness checks.

Requests must carry the shared secret in the `X-Sunny-Token` header (set
SUNNY_HTTP_TOKEN). This endpoint should only be reachable on your own network or
over a private tunnel (e.g. Tailscale) — never exposed raw to the internet.

The routing/auth logic lives in `process_chat` so it can be unit-tested without
opening a socket.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .brain import Brain
from .config import Config


def process_chat(
    brain: Brain, expected_token: str, request_token: str, payload: dict
) -> tuple[int, dict]:
    """Pure core: validate, run the brain, return (status_code, body)."""
    if expected_token and request_token != expected_token:
        return 401, {"error": "unauthorized"}
    message = (payload or {}).get("message", "")
    if not isinstance(message, str) or not message.strip():
        return 400, {"error": "message required"}
    reply = brain.handle(message.strip())
    return 200, {"reply": reply}


def _make_handler(brain: Brain, config: Config):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802 (http.server naming)
            if self.path == "/health":
                self._send(200, {"status": "ok"})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if self.path != "/chat":
                self._send(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._send(400, {"error": "invalid json"})
                return
            token = self.headers.get("X-Sunny-Token", "")
            status, body = process_chat(brain, config.http_token, token, payload)
            self._send(status, body)

        def log_message(self, *args):  # keep the console quiet
            pass

    return Handler


def run_http_server(brain: Brain, config: Config) -> None:
    handler = _make_handler(brain, config)
    server = ThreadingHTTPServer((config.http_host, config.http_port), handler)
    if not config.http_token:
        print("WARNING: SUNNY_HTTP_TOKEN is empty — the API is unauthenticated.")
    print(f"Sunny HTTP API on http://{config.http_host}:{config.http_port} (POST /chat)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
