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
WEB_DIR = Path(__file__).parent / "web"
INDEX_HTML = (WEB_DIR / "index.html").read_text(encoding="utf-8")

# Static assets we serve from web/ (the vendored 3D engine). Mapped by suffix.
_STATIC_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".wasm": "application/wasm",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".svg": "image/svg+xml",
}

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


def _fmt_uptime(secs: int) -> str:
    secs = max(0, int(secs))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def build_status(brain: Brain, config: Config) -> dict:
    """Describe every node (planet), the state of its link to the sun, and live
    telemetry — all from real subsystems, nothing faked."""
    now = time.time()
    brain_state = "online" if config.has_brain else "offline"
    phone_state = "online" if getattr(brain, "phone_online", False) else "offline"
    if config.has_home_assistant:
        home_state = "online" if _ha_reachable(config) else "offline"
    else:
        home_state = "absent"

    store = getattr(brain, "store", None)
    mem_count = store.count_memories() if store else 0
    pending = store.pending_reminders() if store else []
    event_count = store.count_events() if store else 0
    last_events = store.recent_events(12) if store else []
    # The activity-log node lights when something was logged in the last few seconds.
    log_active = bool(last_events) and last_events[0]["created_at"] > now - 4
    briefing_on = bool(getattr(config, "briefing_time", ""))

    def n(node_id, label, state, active=False, info=""):
        return {"id": node_id, "label": label, "state": state, "active": active, "info": info}

    nodes = [
        n("sun", "Sunny", brain_state,
          active=brain.is_active("web") or brain.is_active("phone") or brain.is_active("voice"),
          info=getattr(config, "model", "")),
        n("search", "Web search", brain_state, active=brain.is_active("search")),
        n("memory", "Memory", "online", active=brain.is_active("memory"),
          info=f"{mem_count} items stored"),
        n("phone", "Phone", phone_state, active=brain.is_active("phone"),
          info="connected" if phone_state == "online" else "no bridge"),
        n("watch", "Watch", "absent", info="not linked yet"),
        n("home", "Home Assistant", home_state, active=brain.is_active("home"),
          info="linked" if home_state == "online" else "not configured"),
        n("reminders", "Reminders", "online", active=brain.is_active("reminders"),
          info=f"{len(pending)} pending"),
        n("web", "Web app", "online", active=brain.is_active("web")),
        n("voice", "Voice", "online", active=brain.is_active("voice")),
        # ---- additional real subsystems ----
        n("host", "Host PC", "online",
          info=f"up {_fmt_uptime(now - getattr(brain, 'started_at', now))}"),
        n("upgrade", "Self-upgrade", "online", active=brain.is_active("upgrade"),
          info="sandboxed + approval-gated"),
        n("briefing", "Daily briefing", "online" if briefing_on else "absent",
          active=brain.is_active("briefing"),
          info=f"at {config.briefing_time}" if briefing_on else "not scheduled"),
        n("log", "Activity log", "online", active=log_active,
          info=f"{event_count} events"),
    ]

    telemetry = {
        "model": getattr(config, "model", ""),
        "memories": mem_count,
        "reminders": len(pending),
        "events": event_count,
        "messages": getattr(brain, "message_count", 0),
        "uptime": _fmt_uptime(now - getattr(brain, "started_at", now)),
    }
    feed = [
        {"kind": e["kind"], "detail": e["detail"], "ts": e["created_at"]}
        for e in last_events
    ]
    return {"nodes": nodes, "telemetry": telemetry, "feed": feed}


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

        def _send_static(self, rel_path: str) -> None:
            """Serve a file from web/ (used for the vendored 3D engine).

            Path-traversal safe: the resolved path must stay inside web/.
            """
            try:
                target = (WEB_DIR / rel_path.lstrip("/")).resolve()
                target.relative_to(WEB_DIR.resolve())
            except (ValueError, OSError):
                self._send(404, {"error": "not found"})
                return
            if not target.is_file():
                self._send(404, {"error": "not found"})
                return
            data = target.read_bytes()
            ctype = _STATIC_TYPES.get(target.suffix.lower(), "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            if self.path in ("/", "/index.html"):
                self._send_html(INDEX_HTML.replace("__SUNNY_TOKEN__", config.http_token))
            elif self.path.startswith("/vendor/"):
                self._send_static(self.path.split("?", 1)[0])
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
