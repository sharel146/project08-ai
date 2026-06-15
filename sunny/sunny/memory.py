"""Persistent memory and an activity log, backed by SQLite.

This is what lets Sunny "remember" across restarts. Two tables:
- memories: durable facts/preferences Sunny chooses to keep.
- events: an append-only log of what Sunny did (useful later for her to
  reflect on her own behaviour during self-improvement).
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Memory:
    id: int
    tag: str
    text: str
    created_at: int


@dataclass
class Reminder:
    id: int
    text: str
    due_at: int  # unix seconds
    fired: bool


class Store:
    def __init__(self, db_path: Path | str):
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag TEXT NOT NULL DEFAULT 'note',
                text TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                due_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                fired INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        self._conn.commit()

    # --- memories ---
    def remember(self, text: str, tag: str = "note") -> Memory:
        now = int(time.time())
        cur = self._conn.execute(
            "INSERT INTO memories (tag, text, created_at) VALUES (?, ?, ?)",
            (tag, text, now),
        )
        self._conn.commit()
        return Memory(id=cur.lastrowid, tag=tag, text=text, created_at=now)

    def recall(self, query: str, limit: int = 10) -> list[Memory]:
        """Simple substring search, newest first. Good enough for Phase 1;
        a vector index can replace this later without changing callers."""
        like = f"%{query}%"
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE text LIKE ? OR tag LIKE ? "
            "ORDER BY created_at DESC, id DESC LIMIT ?",
            (like, like, limit),
        ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def recent(self, limit: int = 10) -> list[Memory]:
        rows = self._conn.execute(
            "SELECT * FROM memories ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    # --- reminders ---
    def add_reminder(self, text: str, due_at: int) -> Reminder:
        now = int(time.time())
        cur = self._conn.execute(
            "INSERT INTO reminders (text, due_at, created_at, fired) "
            "VALUES (?, ?, ?, 0)",
            (text, int(due_at), now),
        )
        self._conn.commit()
        return Reminder(id=cur.lastrowid, text=text, due_at=int(due_at), fired=False)

    def pending_reminders(self) -> list[Reminder]:
        rows = self._conn.execute(
            "SELECT * FROM reminders WHERE fired = 0 ORDER BY due_at ASC"
        ).fetchall()
        return [self._row_to_reminder(r) for r in rows]

    def due_reminders(self, now: int) -> list[Reminder]:
        """Reminders that are due (and not yet fired) as of `now`."""
        rows = self._conn.execute(
            "SELECT * FROM reminders WHERE fired = 0 AND due_at <= ? "
            "ORDER BY due_at ASC",
            (int(now),),
        ).fetchall()
        return [self._row_to_reminder(r) for r in rows]

    def mark_fired(self, reminder_id: int) -> None:
        self._conn.execute(
            "UPDATE reminders SET fired = 1 WHERE id = ?", (reminder_id,)
        )
        self._conn.commit()

    @staticmethod
    def _row_to_reminder(r: sqlite3.Row) -> Reminder:
        return Reminder(
            id=r["id"], text=r["text"], due_at=r["due_at"], fired=bool(r["fired"])
        )

    # --- events ---
    def log_event(self, kind: str, detail: str) -> None:
        self._conn.execute(
            "INSERT INTO events (kind, detail, created_at) VALUES (?, ?, ?)",
            (kind, detail, int(time.time())),
        )
        self._conn.commit()

    def recent_events(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT kind, detail, created_at FROM events "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _row_to_memory(r: sqlite3.Row) -> Memory:
        return Memory(id=r["id"], tag=r["tag"], text=r["text"], created_at=r["created_at"])

    def close(self) -> None:
        self._conn.close()
