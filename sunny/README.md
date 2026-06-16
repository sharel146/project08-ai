# Sunny

A personal AI assistant that lives on your PC and reaches you on your phone.

This is **Phase 1** — Sunny's core. She has a Claude-powered brain, a two-way
phone link over [ntfy](https://ntfy.sh), persistent memory, a device-control
tool (mocked for now), and a self-improvement loop that you approve from your
phone before anything ships.

> Sunny is the "brain" in the bigger plan (watch → pocket bridge → Sunny). Build
> her first; the watch and bridge are just her arms and ears later.

## What she can do today

- **Talk to you** from a terminal or your phone.
- **Remember** facts and preferences across restarts (SQLite).
- **Control devices** — a mock registry today; Home Assistant slots in behind the
  same tool later (see "Adding real devices").
- **Push to your phone** proactively.
- **Improve her own code** — she proposes a change, it's tested in an isolated
  sandbox, and you get a phone notification to **approve or reject** before it's
  applied. Nothing self-modifies without your nod.

## Setup (about 5 minutes)

```bash
cd sunny
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set ANTHROPIC_API_KEY and pick unguessable NTFY_TOPIC / NTFY_INBOUND_TOPIC
```

Install the **ntfy** app on your phone (iOS/Android), then:

- **Subscribe** to your `NTFY_TOPIC` → this is where Sunny's messages arrive.
- To talk to her, **send** a message to your `NTFY_INBOUND_TOPIC` from the app.

Test the phone link:

```bash
./run.sh ping      # you should get a "Hello from Sunny" notification
```

## Running her

```bash
./run.sh chat      # talk in your terminal (best for first contact)
./run.sh serve     # 24/7 mode: she listens on the inbox and replies to your phone
./run.sh serve-all # web chat UI + phone bridge together (recommended)
```

### Web chat interface

`serve-all` (or `serve-http`) starts a browser chat UI served by Sunny herself.
Open **http://localhost:8765/** on the PC, or `http://<PC-IP>:8765/` from your
phone on the same network (use a Tailscale IP to reach it from anywhere). Set
`SUNNY_HTTP_TOKEN` in `.env`; the page authenticates with it automatically.

Keep this on your LAN or a private tunnel — don't expose port 8765 to the
public internet.

For always-on, install the systemd unit (`sunny.service`) — see the comments
inside it for Linux/macOS/Windows.

### Always-on on Windows

Use the included `start-sunny.cmd` — it runs `serve` and auto-restarts her if she
ever crashes, logging to `sunny.log`:

1. Double-click `start-sunny.cmd` to start her now.
2. To launch automatically at login: press **Win+R**, type `shell:startup`, Enter,
   and drop a **shortcut** to `start-sunny.cmd` into that folder.

To stop her, close the launcher window. Check `sunny.log` if anything looks off.

## Try the self-improvement loop

In `chat`, ask her something like:

> "Add a friendlier docstring to sunny/tools/devices.py and propose it."

She'll write the change, run the test suite in a throwaway git worktree, and —
if tests pass — send an approval request to your phone. Reply
`approve <id>` or `reject <id>` to the inbox topic. Only on approval is the
change written to your working tree (uncommitted, so you review the diff).

## Adding real devices (later)

`sunny/tools/devices.py` is the only file that knows devices are mocked. Point
`DeviceRegistry.list_devices` / `set_state` at the Home Assistant REST API and
everything above it — the brain, the tools, your phone flow — keeps working.

## Safety model

- **Self-edits are gated**: sandbox test → your approval → apply uncommitted.
  She never edits the live tree directly and never auto-commits.
- **Keep money/identity/irreversible actions behind approval** as you add tools.
  Lights and media can be autonomous; "buy", "delete", "unlock", and "change my
  own code" should always ask first.
- For the self-improvement git sandbox to behave, run Sunny from a git checkout
  where `SUNNY_REPO_ROOT` is the repo root and `SUNNY_TEST_COMMAND` runs the
  tests for that repo.

## Tests

```bash
python -m pytest -q
```

## What's next (later phases)

- Phase 2: wire `devices.py` to Home Assistant; add the watch/bridge front-end.
- Phase 3: richer memory, voice, and broader automations.
