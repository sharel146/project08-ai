"""Entry point for Sunny.

Usage:
  python -m sunny.main chat       # talk to Sunny in your terminal (good for dev)
  python -m sunny.main serve      # run 24/7: listen on the ntfy inbox, reply to phone
  python -m sunny.main serve-http # run the HTTP API so the watch app can reach her
  python -m sunny.main ping       # send a test push to your phone and exit
"""

from __future__ import annotations

import sys
import time

from .brain import Brain
from .config import Config
from .memory import Store
from .notifier import Notifier
from .tools.devices import DeviceRegistry
from .tools.self_improve import SelfImprover


def _build(config: Config) -> Brain:
    store = Store(config.db_path)
    notifier = Notifier(
        config.ntfy_server, config.ntfy_outbound_topic, config.ntfy_inbound_topic
    )
    devices = DeviceRegistry.with_demo_devices()
    improver = SelfImprover(config.repo_root, config.test_command)
    return Brain(config, store, notifier, devices, improver)


def cmd_chat(config: Config) -> int:
    if not config.has_brain:
        print("ANTHROPIC_API_KEY is not set — Sunny has no brain to talk with.")
        return 1
    brain = _build(config)
    print("Sunny is awake. Type a message (Ctrl-C to quit).")
    try:
        while True:
            user = input("you> ").strip()
            if not user:
                continue
            print(f"sunny> {brain.handle(user)}")
    except (EOFError, KeyboardInterrupt):
        print("\nSunny going to sleep.")
        return 0


def cmd_serve(config: Config) -> int:
    if not config.has_brain:
        print("ANTHROPIC_API_KEY is not set — cannot serve.")
        return 1
    brain = _build(config)
    brain.notifier.push(
        "Sunny is online and listening.", title="Sunny", tags=["sunrise"]
    )
    print(
        f"Serving. Send messages to the '{config.ntfy_inbound_topic}' topic; "
        f"replies go to '{config.ntfy_outbound_topic}'."
    )
    since = int(time.time())
    while True:
        try:
            # One long-lived streaming connection (not rapid polling, which
            # ntfy.sh rate-limits with HTTP 429). Each event — a message or a
            # keepalive tick — is also our cue to fire any due reminders.
            for event in brain.notifier.stream_inbound(since=since):
                for rem in brain.store.due_reminders(int(time.time())):
                    brain.notifier.push(rem.text, title="Reminder", tags=["alarm_clock"])
                    brain.store.mark_fired(rem.id)

                if event is None:
                    continue  # keepalive tick, nothing to reply to

                since = max(since, event.time + 1)
                text = event.text.strip()
                # Approve/reject replies are consumed by the approval gate, not here.
                if text.lower().startswith(("approve ", "reject ")):
                    continue
                reply = brain.handle(text)
                brain.notifier.push(reply, title="Sunny")
            time.sleep(1)  # connection closed normally; reconnect promptly
        except KeyboardInterrupt:
            print("\nStopped.")
            return 0
        except Exception as exc:  # transient drop / rate limit — back off, reconnect
            print(f"[serve] connection issue ({exc}); reconnecting in 20s…")
            time.sleep(20)


def cmd_serve_http(config: Config) -> int:
    if not config.has_brain:
        print("ANTHROPIC_API_KEY is not set — cannot serve.")
        return 1
    from .server import run_http_server

    brain = _build(config)
    run_http_server(brain, config)
    return 0


def cmd_ping(config: Config) -> int:
    notifier = Notifier(
        config.ntfy_server, config.ntfy_outbound_topic, config.ntfy_inbound_topic
    )
    notifier.push("Hello from Sunny 👋", title="Sunny test", tags=["wave"])
    print(f"Pushed a test notification to '{config.ntfy_outbound_topic}'.")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    command = argv[0] if argv else "chat"
    config = Config.from_env()
    if command == "chat":
        return cmd_chat(config)
    if command == "serve":
        return cmd_serve(config)
    if command == "serve-http":
        return cmd_serve_http(config)
    if command == "ping":
        return cmd_ping(config)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
