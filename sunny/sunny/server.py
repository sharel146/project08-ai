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
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#ff8a4c">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Sunny">
<title>Sunny</title>
<style>
  :root {
    --bg1:#fff6ea; --bg2:#ffe9d6; --panel:#ffffff; --panel-2:#fbf3ea;
    --text:#2c2420; --muted:#9a8c7e; --line:#f0e4d6;
    --her-bg:#ffffff; --her-border:#f1e6d8;
    --me-grad:linear-gradient(135deg,#ffb070,#ff7a59);
    --accent:#ff7a4d; --shadow:0 6px 22px rgba(120,80,40,.10);
    --header:linear-gradient(110deg,#ffd36b 0%,#ff9e5e 48%,#ff7d8b 100%);
  }
  [data-theme="dark"] {
    --bg1:#15110e; --bg2:#1e1813; --panel:#241d18; --panel-2:#1c1611;
    --text:#f4ece2; --muted:#a89a8b; --line:#352b22;
    --her-bg:#2a221c; --her-border:#382d24;
    --me-grad:linear-gradient(135deg,#ff9e5e,#ff6f4d);
    --accent:#ff9e5e; --shadow:0 8px 26px rgba(0,0,0,.35);
    --header:linear-gradient(110deg,#caa24a 0%,#d97a44 50%,#c25767 100%);
  }
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  html,body { height:100%; }
  body {
    margin:0; display:flex; flex-direction:column;
    height:100dvh; min-height:100vh;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
    color:var(--text);
    background:linear-gradient(160deg,var(--bg1),var(--bg2));
    transition:background .3s,color .3s;
  }
  header {
    display:flex; align-items:center; gap:12px;
    padding:14px 16px; padding-top:calc(14px + env(safe-area-inset-top));
    background:var(--header); color:#3a2415; box-shadow:0 2px 14px rgba(180,110,60,.25);
    position:relative; z-index:2;
  }
  .sun {
    width:34px; height:34px; border-radius:50%; flex:none;
    background:radial-gradient(circle at 38% 35%,#fff3c4,#ffd24d 45%,#ff9e2c 75%);
    box-shadow:0 0 0 4px rgba(255,255,255,.35), 0 2px 8px rgba(180,110,30,.5);
  }
  header .title { font-weight:800; font-size:20px; letter-spacing:.2px; }
  header .sub { font-size:12px; opacity:.8; margin-top:-2px; }
  header .grow { flex:1; }
  .iconbtn {
    border:none; width:38px; height:38px; border-radius:50%;
    background:rgba(255,255,255,.28); color:#3a2415; cursor:pointer;
    font-size:17px; display:grid; place-items:center; transition:background .15s;
  }
  .iconbtn:hover { background:rgba(255,255,255,.45); }

  #log { flex:1; overflow-y:auto; padding:18px 14px 8px; display:flex; flex-direction:column; gap:14px; scroll-behavior:smooth; }
  .row { display:flex; gap:9px; align-items:flex-end; max-width:88%; animation:pop .22s ease; }
  .row.me { align-self:flex-end; flex-direction:row-reverse; }
  .row.her { align-self:flex-start; }
  .ava { width:28px; height:28px; border-radius:50%; flex:none;
    background:radial-gradient(circle at 38% 35%,#fff3c4,#ffd24d 45%,#ff9e2c 78%);
    box-shadow:0 1px 5px rgba(180,110,30,.4); }
  .stack { display:flex; flex-direction:column; gap:3px; min-width:0; }
  .bubble {
    padding:11px 14px; border-radius:18px; line-height:1.45; font-size:15.5px;
    word-wrap:break-word; overflow-wrap:anywhere; box-shadow:var(--shadow);
  }
  .me .bubble { background:var(--me-grad); color:#fff; border-bottom-right-radius:6px; }
  .her .bubble { background:var(--her-bg); border:1px solid var(--her-border); border-bottom-left-radius:6px; }
  .bubble a { color:inherit; font-weight:600; text-decoration:underline; }
  .her .bubble a { color:var(--accent); }
  .bubble code { background:rgba(127,127,127,.18); padding:1px 5px; border-radius:6px; font-size:.92em; }
  .time { font-size:11px; color:var(--muted); padding:0 6px; }
  .me .time { text-align:right; }

  .typing .bubble { display:inline-flex; gap:5px; align-items:center; }
  .dot { width:7px; height:7px; border-radius:50%; background:var(--muted); animation:blink 1.3s infinite; }
  .dot:nth-child(2){ animation-delay:.2s; } .dot:nth-child(3){ animation-delay:.4s; }

  #chips { display:flex; flex-wrap:wrap; gap:8px; padding:4px 16px 10px; }
  .chip {
    border:1px solid var(--line); background:var(--panel); color:var(--text);
    padding:8px 13px; border-radius:999px; font-size:13.5px; cursor:pointer; box-shadow:var(--shadow);
    transition:transform .12s, border-color .15s;
  }
  .chip:hover { transform:translateY(-1px); border-color:var(--accent); }

  form {
    display:flex; gap:9px; align-items:flex-end; padding:10px 12px;
    padding-bottom:calc(10px + env(safe-area-inset-bottom));
    background:var(--panel-2); border-top:1px solid var(--line);
  }
  #input {
    flex:1; resize:none; border:1px solid var(--line); border-radius:22px;
    padding:12px 16px; font-size:16px; line-height:1.35; max-height:140px;
    background:var(--panel); color:var(--text); font-family:inherit; outline:none;
  }
  #input:focus { border-color:var(--accent); }
  #send {
    border:none; width:46px; height:46px; border-radius:50%; flex:none; cursor:pointer;
    background:var(--me-grad); color:#fff; font-size:20px; display:grid; place-items:center;
    box-shadow:0 4px 14px rgba(255,120,80,.45); transition:transform .12s,opacity .15s;
  }
  #send:active { transform:scale(.92); }
  #send:disabled { opacity:.45; cursor:default; box-shadow:none; }

  @keyframes pop { from { opacity:0; transform:translateY(6px); } to { opacity:1; transform:none; } }
  @keyframes blink { 0%,60%,100%{ opacity:.25; } 30%{ opacity:1; } }
</style>
</head>
<body>
<header>
  <div class="sun"></div>
  <div>
    <div class="title">Sunny</div>
    <div class="sub">your assistant</div>
  </div>
  <div class="grow"></div>
  <button class="iconbtn" id="theme" title="Toggle theme">&#9790;</button>
  <button class="iconbtn" id="newchat" title="New chat">&#10227;</button>
</header>

<div id="log"></div>
<div id="chips"></div>

<form id="form">
  <textarea id="input" rows="1" placeholder="Message Sunny…" autocomplete="off"></textarea>
  <button id="send" type="submit" title="Send">&#10148;</button>
</form>

<script>
  const TOKEN = "__SUNNY_TOKEN__";
  const STORE = "sunny_chat_v1";
  const log = document.getElementById("log");
  const chips = document.getElementById("chips");
  const form = document.getElementById("form");
  const input = document.getElementById("input");
  const send = document.getElementById("send");
  const SUGGESTIONS = ["What's the weather today?", "Remind me to drink water in 1 hour", "What can you do?", "Give me a fun fact"];

  let history = [];
  try { history = JSON.parse(localStorage.getItem(STORE) || "[]"); } catch (e) { history = []; }

  // theme
  const savedTheme = localStorage.getItem("sunny_theme");
  if (savedTheme) document.documentElement.setAttribute("data-theme", savedTheme);
  function curTheme(){ return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light"; }
  document.getElementById("theme").onclick = () => {
    const t = curTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem("sunny_theme", t);
    document.getElementById("theme").innerHTML = t === "dark" ? "&#9728;" : "&#9790;";
  };
  document.getElementById("theme").innerHTML = curTheme() === "dark" ? "&#9728;" : "&#9790;";

  function escapeHtml(s){ return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
  function fmt(text){
    let h = escapeHtml(text);
    const links = [];
    h = h.replace(/\\[([^\\]]+)\\]\\((https?:\\/\\/[^)\\s]+)\\)/g, (m,t,u) => {
      links.push('<a href="'+u+'" target="_blank" rel="noopener">'+t+'</a>');
      return "\\u0000"+(links.length-1)+"\\u0000";
    });
    h = h.replace(/(https?:\\/\\/[^\\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
    h = h.replace(/`([^`]+)`/g, "<code>$1</code>");
    h = h.replace(/\\*\\*([^*]+)\\*\\*/g, "<strong>$1</strong>");
    h = h.replace(/(^|[^*])\\*([^*\\n]+)\\*/g, "$1<em>$2</em>");
    h = h.replace(/\\u0000(\\d+)\\u0000/g, (m,i) => links[+i]);
    return h.replace(/\\n/g, "<br>");
  }
  function clock(ts){ const d = new Date(ts); return d.toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"}); }

  function render(role, text, ts, save){
    const row = document.createElement("div");
    row.className = "row " + (role === "me" ? "me" : "her");
    const ava = role === "me" ? "" : '<div class="ava"></div>';
    row.innerHTML = ava +
      '<div class="stack"><div class="bubble">'+fmt(text)+'</div>'+
      '<div class="time">'+clock(ts)+'</div></div>';
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
    if (save){ history.push({role, text, ts}); localStorage.setItem(STORE, JSON.stringify(history.slice(-120))); }
    return row;
  }

  function showChips(){
    chips.innerHTML = "";
    if (history.length) return;
    SUGGESTIONS.forEach(s => {
      const c = document.createElement("button");
      c.className = "chip"; c.type = "button"; c.textContent = s;
      c.onclick = () => ask(s);
      chips.appendChild(c);
    });
  }

  function typing(){
    const row = document.createElement("div");
    row.className = "row her typing";
    row.innerHTML = '<div class="ava"></div><div class="stack"><div class="bubble"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div></div>';
    log.appendChild(row); log.scrollTop = log.scrollHeight;
    return row;
  }

  async function ask(text){
    chips.innerHTML = "";
    render("me", text, Date.now(), true);
    const t = typing(); send.disabled = true;
    try {
      const res = await fetch("/chat", {
        method:"POST",
        headers:{ "Content-Type":"application/json", "X-Sunny-Token":TOKEN },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      t.remove();
      render("her", res.ok ? (data.reply || "(no reply)") : ("Error: " + (data.error || res.status)), Date.now(), true);
    } catch (e) {
      t.remove();
      render("her", "Couldn't reach Sunny — is she running? (" + e + ")", Date.now(), true);
    } finally {
      send.disabled = false; input.focus();
    }
  }

  document.getElementById("newchat").onclick = async () => {
    history = []; localStorage.removeItem(STORE); log.innerHTML = "";
    try { await fetch("/reset", { method:"POST", headers:{ "X-Sunny-Token":TOKEN } }); } catch (e) {}
    render("her", "Fresh start! What's on your mind?", Date.now(), false);
    showChips();
  };

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim(); if (!text) return;
    input.value = ""; input.style.height = "auto";
    ask(text);
  });
  input.addEventListener("input", () => {
    input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px";
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });

  // initial render
  if (history.length){ history.forEach(m => render(m.role, m.text, m.ts, false)); }
  else { render("her", "Hi, I'm Sunny \\u2600\\ufe0f  Ask me anything, set a reminder, or tap a suggestion.", Date.now(), false); }
  showChips();
  input.focus();
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
            token = self.headers.get("X-Sunny-Token", "")
            if self.path == "/reset":
                if config.http_token and token != config.http_token:
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
