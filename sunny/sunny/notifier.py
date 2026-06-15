"""The phone bridge: a thin wrapper around ntfy (https://ntfy.sh).

ntfy is pub/sub over plain HTTP. Sunny *publishes* to an outbound topic to
reach your phone, and *polls* an inbound topic to hear from you. You install
the ntfy app, subscribe to the outbound topic to get notifications, and send
messages (or "approve <id>" / "reject <id>") to the inbound topic to talk back.

No account or API key is needed for the public ntfy.sh server; pick unguessable
topic names since anyone who knows a topic can read and write it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import requests


@dataclass
class IncomingMessage:
    text: str
    time: int  # unix seconds, from ntfy
    id: str


def build_publish_request(
    server: str,
    topic: str,
    message: str,
    title: str | None = None,
    priority: str | None = None,
    tags: Iterable[str] | None = None,
) -> tuple[str, bytes, dict[str, str]]:
    """Pure helper: build (url, body, headers) for a publish. Kept separate from
    the network call so it can be unit-tested without hitting ntfy."""
    url = f"{server.rstrip('/')}/{topic}"
    headers: dict[str, str] = {}
    if title:
        # ntfy headers must be latin-1 safe; encode anything fancy.
        headers["Title"] = title.encode("utf-8").decode("latin-1", "replace")
    if priority:
        headers["Priority"] = priority
    if tags:
        headers["Tags"] = ",".join(tags)
    return url, message.encode("utf-8"), headers


class Notifier:
    def __init__(
        self,
        server: str,
        outbound_topic: str,
        inbound_topic: str,
        *,
        session: requests.Session | None = None,
        dry_run: bool = False,
    ):
        self.server = server.rstrip("/")
        self.outbound_topic = outbound_topic
        self.inbound_topic = inbound_topic
        self._session = session or requests.Session()
        self.dry_run = dry_run

    def push(
        self,
        message: str,
        title: str | None = None,
        priority: str | None = None,
        tags: Iterable[str] | None = None,
    ) -> None:
        """Send a notification to your phone."""
        url, body, headers = build_publish_request(
            self.server, self.outbound_topic, message, title, priority, tags
        )
        if self.dry_run:
            print(f"[notifier dry-run] -> {title or ''}: {message}")
            return
        self._session.post(url, data=body, headers=headers, timeout=15).raise_for_status()

    def poll_inbound(self, since: int) -> list[IncomingMessage]:
        """Fetch messages sent to the inbound topic at or after `since` (unix s).

        Uses ntfy's poll mode (?poll=1) so this returns immediately instead of
        holding a long-lived stream — simpler and reconnection-free.
        """
        if self.dry_run:
            return []
        url = f"{self.server}/{self.inbound_topic}/json"
        resp = self._session.get(
            url, params={"poll": "1", "since": str(since)}, timeout=30
        )
        resp.raise_for_status()
        out: list[IncomingMessage] = []
        for line in resp.text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = requests.compat.json.loads(line)  # type: ignore[attr-defined]
            except Exception:
                continue
            if obj.get("event") != "message":
                continue  # skip keepalive/open events
            out.append(
                IncomingMessage(
                    text=obj.get("message", ""),
                    time=int(obj.get("time", since)),
                    id=str(obj.get("id", "")),
                )
            )
        return out
