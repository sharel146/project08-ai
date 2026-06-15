"""Configuration for Sunny, loaded from environment variables.

Everything Sunny needs to run is read here so the rest of the code never
touches os.environ directly. Copy .env.example to .env and fill it in, then
load it (run.sh does this for you) before starting Sunny.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _repo_root() -> Path:
    # sunny/sunny/config.py -> repo root is two parents up from this file's package.
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    # --- Brain ---
    anthropic_api_key: str
    model: str
    effort: str

    # --- Phone bridge (ntfy) ---
    ntfy_server: str
    ntfy_outbound_topic: str  # Sunny -> your phone
    ntfy_inbound_topic: str   # your phone -> Sunny (and approve/reject replies)

    # --- Storage ---
    db_path: Path

    # --- Self-improvement ---
    repo_root: Path
    test_command: str
    approval_timeout_seconds: int

    # --- Loop ---
    poll_interval_seconds: float

    # --- HTTP API (so the watch / other clients can talk to Sunny) ---
    http_host: str
    http_port: int
    http_token: str

    @property
    def has_brain(self) -> bool:
        return bool(self.anthropic_api_key)

    @classmethod
    def from_env(cls) -> "Config":
        root = Path(os.environ.get("SUNNY_REPO_ROOT", str(_repo_root())))
        return cls(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            model=os.environ.get("SUNNY_MODEL", "claude-opus-4-8"),
            effort=os.environ.get("SUNNY_EFFORT", "high"),
            ntfy_server=os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/"),
            ntfy_outbound_topic=os.environ.get("NTFY_TOPIC", "sunny-updates"),
            ntfy_inbound_topic=os.environ.get(
                "NTFY_INBOUND_TOPIC", "sunny-inbox"
            ),
            db_path=Path(os.environ.get("SUNNY_DB_PATH", str(root / "sunny.db"))),
            repo_root=root,
            test_command=os.environ.get("SUNNY_TEST_COMMAND", "python -m pytest -q"),
            approval_timeout_seconds=int(
                os.environ.get("SUNNY_APPROVAL_TIMEOUT", "300")
            ),
            poll_interval_seconds=float(os.environ.get("SUNNY_POLL_INTERVAL", "3")),
            http_host=os.environ.get("SUNNY_HTTP_HOST", "0.0.0.0"),
            http_port=int(os.environ.get("SUNNY_HTTP_PORT", "8765")),
            http_token=os.environ.get("SUNNY_HTTP_TOKEN", ""),
        )
