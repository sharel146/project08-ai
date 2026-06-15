"""Human-in-the-loop approval gate over the ntfy phone bridge.

Sunny pushes a proposal to your phone with a short id, then watches the inbound
topic for a reply of "approve <id>" or "reject <id>". This is the safety
mechanism behind self-improvement and any other action that should never happen
without your nod.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from .notifier import Notifier


@dataclass
class ApprovalResult:
    approved: bool
    reason: str  # "approved", "rejected", or "timeout"


def new_approval_id() -> str:
    return uuid.uuid4().hex[:6]


def _decision_for(text: str, approval_id: str) -> bool | None:
    """Parse a reply. Returns True/False for a decision about this id, or None
    if the message isn't about it."""
    norm = text.strip().lower()
    if approval_id.lower() not in norm:
        return None
    if norm.startswith("approve") or norm.startswith("yes") or norm.startswith("ok"):
        return True
    if norm.startswith("reject") or norm.startswith("no") or norm.startswith("deny"):
        return False
    return None


def request_approval(
    notifier: Notifier,
    summary: str,
    *,
    timeout_seconds: int = 300,
    poll_interval: float = 3.0,
    approval_id: str | None = None,
    _now=time.time,
    _sleep=time.sleep,
) -> ApprovalResult:
    """Ask for approval and block until a decision or timeout."""
    approval_id = approval_id or new_approval_id()
    start = int(_now())
    notifier.push(
        message=(
            f"{summary}\n\n"
            f"Reply 'approve {approval_id}' or 'reject {approval_id}' "
            f"to the {notifier.inbound_topic} topic."
        ),
        title="Sunny needs your approval",
        priority="high",
        tags=["warning"],
    )

    deadline = start + timeout_seconds
    while int(_now()) <= deadline:
        for msg in notifier.poll_inbound(since=start):
            decision = _decision_for(msg.text, approval_id)
            if decision is True:
                return ApprovalResult(True, "approved")
            if decision is False:
                return ApprovalResult(False, "rejected")
        _sleep(poll_interval)

    return ApprovalResult(False, "timeout")
