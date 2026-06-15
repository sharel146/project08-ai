"""The phone bridge: a thin wrapper around ntfy (https://ntfy.sh).

ntfy is pub/sub over plain HTTP. Sunny *publishes* to an outbound topic to
reach your phone, and *polls* an inbound topic to hear from you. You install
the ntfy app, subscribe to the outbound topic to get notifications, and send
messages (or "approve <id>" / "reject <id>") to the inbound topic to talk back.

No account or API key is needed for the public ntfy.sh server; pick unguessable
topic names since anyone who knows a topic can read and write it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, Iterator

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

        Uses ntfy's poll mode (?poll=1). This makes a one-shot request, so it's
        only used for short, infrequent waits (e.g. the approval gate). For the
        always-on serve loop, use stream_inbound() instead — repeated polling
        gets rate-limited (HTTP 429) by ntfy.sh.
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
            msg = self._parse_line(line, since)
            if msg is not None:
                out.append(msg)
        return out

    def stream_inbound(self, since: int) -> Iterator["IncomingMessage | None"]:
        """Hold ONE long-lived connection to the inbound topic and yield messages
        as they arrive. Yields None on ntfy keepalive ticks so the caller can do
        periodic work (e.g. checking reminders). Replays anything since `since`
        on connect, then streams live. Raises when the connection drops — the
        caller should reconnect.

        This is the correct, rate-limit-friendly way to receive: one open
        request instead of a poll every few seconds.
        """
        if self.dry_run:
            return
        url = f"{self.server}/{self.inbound_topic}/json"
        with self._session.get(
            url, params={"since": str(since)}, stream=True, timeout=(10, 90)
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    continue
                event = obj.get("event")
                if event == "message":
                    yield IncomingMessage(
                        text=obj.get("message", ""),
                        time=int(obj.get("time", since)),
                        id=str(obj.get("id", "")),
                    )
                elif event in ("keepalive", "open"):
                    yield None  # tick for periodic work

    @staticmethod
    def _parse_line(line: str, since: int) -> "IncomingMessage | None":
        line = line.strip()
        if not line:
            return None
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            return None
        if obj.get("event") != "message":
            return None  # skip keepalive/open events
        return IncomingMessage(
            text=obj.get("message", ""),
            time=int(obj.get("time", since)),
            id=str(obj.get("id", "")),
        )
