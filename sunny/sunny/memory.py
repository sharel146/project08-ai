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
