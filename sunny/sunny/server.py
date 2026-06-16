"""A small HTTP server: the solar-system web app + chat/voice + a status feed.

Routes:
    GET  /            -> the solar-system dashboard (HTML, token injected)
    GET  /status      -> live connectivity of every "planet" (for the strings)
    POST /chat        -> {"message": "..."}  -> {"reply": "..."}
    POST /reset       -> start a fresh conversation
    GET  /health      -> liveness

Requests (except /, /health) must carry the shared secret in X-Sunny-Token.
Keep this reachable only on your LAN or a private tunnel (e.g. Tailscale).
"""

from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

from .brain import Brain
from .config import Config

# The page lives in a real file (raw HTML/JS — no Python escaping headaches).
INDEX_HTML = (Path(__file__).parent / "web" / "index.html").read_text(encoding="utf-8")

# Cache Home Assistant reachability so /status doesn't ping it on every poll.
_ha_cache = {"ts": 0.0, "ok": False}


def _ha_reachable(config: Config) -> bool:
    now = time.time()
    if now - _ha_cache["ts"] < 10:
        return _ha_cache["ok"]
    ok = False
    try:
        resp = requests.get(
            f"{config.ha_url}/api/",
            headers={"Authorization": f"Bearer {config.ha_token}"},
            timeout=2.5,
        )
        ok = resp.status_code == 200
    except requests.RequestException:
        ok = False
    _ha_cache.update(ts=now, ok=ok)
    return ok


def build_status(brain: Brain, config: Config) -> dict:
    """Describe every node (planet) and the state of its string to the sun."""
    brain_state = "online" if config.has_brain else "offline"
    phone_state = "online" if getattr(brain, "phone_online", False) else "offline"
    if config.has_home_assistant:
        home_state = "online" if _ha_reachable(config) else "offline"
    else:
        home_state = "absent"

    def n(node_id, label, state, active=False):
        return {"id": node_id, "label": label, "state": state, "active": active}

    nodes = [
        n("sun", "Sunny", brain_state,
          active=brain.is_active("web") or brain.is_active("phone") or brain.is_active("voice")),
        n("search", "Web search", brain_state),
        n("memory", "Memory", "online"),
        n("phone", "Phone", phone_state, active=brain.is_active("phone")),
        n("watch", "Watch", "absent"),
        n("home", "Home Assistant", home_state),
        n("reminders", "Reminders", "online"),
        n("web", "Web app", "online", active=brain.is_active("web")),
        n("voice", "Voice", "online", active=brain.is_active("voice")),
    ]
    return {"nodes": nodes}


def process_chat(
    brain: Brain, expected_token: str, request_token: str, payload: dict
) -> tuple[int, dict]:
    """Pure core: validate, run the brain, return (status_code, body)."""
    if expected_token and request_token != expected_token:
        return 401, {"error": "unauthorized"}
    message = (payload or {}).get("message", "")
    if not isinstance(message, str) or not message.strip():
        return 400, {"error": "message required"}
    brain.mark_active("web")
    reply = brain.handle(message.strip())
    return 200, {"reply": reply}


def _make_handler(brain: Brain, config: Config):
    def authed(headers) -> bool:
        return (not config.http_token) or headers.get("X-Sunny-Token", "") == config.http_token

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_html(self, html: str) -> None:
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            if self.path in ("/", "/index.html"):
                self._send_html(INDEX_HTML.replace("__SUNNY_TOKEN__", config.http_token))
            elif self.path == "/status":
                if not authed(self.headers):
                    self._send(401, {"error": "unauthorized"})
                    return
                self._send(200, build_status(brain, config))
            elif self.path == "/health":
                self._send(200, {"status": "ok"})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if self.path == "/reset":
                if not authed(self.headers):
                    self._send(401, {"error": "unauthorized"})
                    return
                brain.reset()
                self._send(200, {"status": "ok"})
                return
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
    print(
        f"Sunny web app at http://localhost:{config.http_port}/  "
        f"(open it in a browser). Keep it on your LAN or a private tunnel."
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
