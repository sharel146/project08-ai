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

# A self-contained chat page. __SUNNY_TOKEN__ is replaced with the API token at
# serve time so the page can authenticate to /chat from the same origin.
INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sunny</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0; height: 100vh; display: flex; flex-direction: column;
    font-family: -apple-system, Segoe UI, Roboto, sans-serif;
    background: linear-gradient(135deg, #1a1530, #2a2150, #1e1b3a); color: #fff;
  }
  header {
    padding: 16px; font-size: 20px; font-weight: 600; text-align: center;
    background: rgba(255,255,255,0.06); border-bottom: 1px solid rgba(255,255,255,0.08);
  }
  #log { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
  .msg { max-width: 78%; padding: 10px 14px; border-radius: 16px; line-height: 1.4; white-space: pre-wrap; word-wrap: break-word; }
  .me { align-self: flex-end; background: #1f6feb; border-bottom-right-radius: 4px; }
  .her { align-self: flex-start; background: rgba(255,255,255,0.12); border-bottom-left-radius: 4px; }
  .typing { opacity: 0.7; font-style: italic; }
  form { display: flex; gap: 8px; padding: 12px; background: rgba(0,0,0,0.2); }
  #input {
    flex: 1; resize: none; border-radius: 20px; border: none; padding: 12px 16px;
    font-size: 16px; background: rgba(255,255,255,0.95); color: #111; max-height: 120px;
  }
  button {
    border: none; border-radius: 20px; padding: 0 20px; font-size: 16px; font-weight: 600;
    background: #ffd166; color: #1a1530; cursor: pointer;
  }
  button:disabled { opacity: 0.5; cursor: default; }
</style>
</head>
<body>
<header>Sunny &#9728;</header>
<div id="log"></div>
<form id="form">
  <textarea id="input" rows="1" placeholder="Message Sunny…" autocomplete="off"></textarea>
  <button id="send" type="submit">Send</button>
</form>
<script>
  const TOKEN = "__SUNNY_TOKEN__";
  const log = document.getElementById("log");
  const form = document.getElementById("form");
  const input = document.getElementById("input");
  const send = document.getElementById("send");

  function bubble(text, cls) {
    const div = document.createElement("div");
    div.className = "msg " + cls;
    div.textContent = text;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
    return div;
  }

  bubble("Hi! I'm Sunny. Ask me anything.", "her");

  async function ask(text) {
    bubble(text, "me");
    const typing = bubble("Sunny is typing…", "her typing");
    send.disabled = true;
    try {
      const res = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Sunny-Token": TOKEN },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      typing.remove();
      bubble(res.ok ? (data.reply || "(no reply)") : ("Error: " + (data.error || res.status)), "her");
    } catch (e) {
      typing.remove();
      bubble("Couldn't reach Sunny: " + e, "her");
    } finally {
      send.disabled = false;
      input.focus();
    }
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    ask(text);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });
</script>
</body>
</html>"""


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

        def _send_html(self, html: str) -> None:
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802 (http.server naming)
            if self.path in ("/", "/index.html"):
                self._send_html(INDEX_HTML.replace("__SUNNY_TOKEN__", config.http_token))
            elif self.path == "/health":
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
    print(
        f"Sunny web chat at http://localhost:{config.http_port}/  "
        f"(open it in a browser). Keep it on your LAN or a private tunnel."
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
