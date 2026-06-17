"""Configuration for Sunny, loaded from environment variables.

Everything Sunny needs to run is read here so the rest of the code never
touches os.environ directly. Copy .env.example to .env and fill it in, then
load it (run.sh does this for you) before starting Sunny.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _repo_root() -> Path:
    # sunny/sunny/config.py -> repo root is two parents up from this file's package.
    return Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines from a .env file into os.environ.

    Real environment variables always win (we never overwrite them). This means
    `python -m sunny.main ...` works on Windows without a shell wrapper — you
    don't need run.sh to source the file.
    """
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


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

    # --- Home Assistant (optional; real device control when set) ---
    ha_url: str
    ha_token: str

    # --- Daily briefing (optional; "HH:MM" local, empty = off) ---
    briefing_time: str

    @property
    def has_brain(self) -> bool:
        return bool(self.anthropic_api_key)

    @classmethod
    def from_env(cls) -> "Config":
        # Auto-load .env from the working directory, then from the repo root,
        # so Sunny is configured the same way on every platform.
        _load_dotenv(Path.cwd() / ".env")
        root = Path(os.environ.get("SUNNY_REPO_ROOT", str(_repo_root())))
        _load_dotenv(root / ".env")
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
            # Use the SAME interpreter Sunny runs under, not a bare "python" that
            # may resolve to a different (venv-less) Python in the test subprocess.
            test_command=os.environ.get(
                "SUNNY_TEST_COMMAND", f'"{sys.executable}" -m pytest -q'
            ),
            approval_timeout_seconds=int(
                os.environ.get("SUNNY_APPROVAL_TIMEOUT", "300")
            ),
            poll_interval_seconds=float(os.environ.get("SUNNY_POLL_INTERVAL", "3")),
            http_host=os.environ.get("SUNNY_HTTP_HOST", "0.0.0.0"),
            http_port=int(os.environ.get("SUNNY_HTTP_PORT", "8765")),
            http_token=os.environ.get("SUNNY_HTTP_TOKEN", ""),
            ha_url=os.environ.get("HA_URL", "").rstrip("/"),
            ha_token=os.environ.get("HA_TOKEN", ""),
            briefing_time=os.environ.get("SUNNY_BRIEFING_TIME", ""),
        )

    @property
    def has_home_assistant(self) -> bool:
        return bool(self.ha_url and self.ha_token)
