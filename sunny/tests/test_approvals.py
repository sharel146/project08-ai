from sunny.approvals import _decision_for, request_approval
from sunny.notifier import IncomingMessage


def test_decision_parsing():
    assert _decision_for("approve ab12", "ab12") is True
    assert _decision_for("reject ab12", "ab12") is False
    assert _decision_for("yes ab12 please", "ab12") is True
    assert _decision_for("approve other", "ab12") is None
    assert _decision_for("hello", "ab12") is None


class FakeNotifier:
    """Stands in for the real Notifier so approvals can be tested offline."""

    inbound_topic = "sunny-inbox"

    def __init__(self, replies):
        self._replies = replies
        self.pushed = []

    def push(self, message, title=None, priority=None, tags=None):
        self.pushed.append(message)

    def poll_inbound(self, since):
        return self._replies


def test_request_approval_approved():
    notifier = FakeNotifier([IncomingMessage("approve zz99", time=10, id="1")])
    result = request_approval(
        notifier, "do the thing", approval_id="zz99",
        timeout_seconds=5, poll_interval=0,
        _now=lambda: 0, _sleep=lambda s: None,
    )
    assert result.approved is True
    assert notifier.pushed  # the proposal was sent


def test_request_approval_timeout():
    notifier = FakeNotifier([])  # no replies ever
    clock = {"t": 0}

    def now():
        clock["t"] += 1
        return clock["t"]

    result = request_approval(
        notifier, "do the thing", approval_id="zz99",
        timeout_seconds=2, poll_interval=0,
        _now=now, _sleep=lambda s: None,
    )
    assert result.approved is False
    assert result.reason == "timeout"
