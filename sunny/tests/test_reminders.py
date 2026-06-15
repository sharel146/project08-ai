import time

from sunny.memory import Store


def test_add_and_list_pending(tmp_path):
    store = Store(tmp_path / "t.db")
    store.add_reminder("call mom", due_at=2000)
    store.add_reminder("take meds", due_at=1000)
    pending = store.pending_reminders()
    # Sorted by due time, earliest first.
    assert [r.text for r in pending] == ["take meds", "call mom"]
    assert all(r.fired is False for r in pending)


def test_due_reminders_respects_time_and_fired(tmp_path):
    store = Store(tmp_path / "t.db")
    past = store.add_reminder("past one", due_at=int(time.time()) - 10)
    store.add_reminder("future one", due_at=int(time.time()) + 3600)

    due = store.due_reminders(int(time.time()))
    assert [r.text for r in due] == ["past one"]

    # Once fired, it should not come due again.
    store.mark_fired(past.id)
    assert store.due_reminders(int(time.time())) == []
    assert [r.text for r in store.pending_reminders()] == ["future one"]


def test_cancel_reminder(tmp_path):
    store = Store(tmp_path / "t.db")
    r = store.add_reminder("cancel me", due_at=int(time.time()) + 3600)
    assert store.cancel_reminder(r.id) is True
    assert store.pending_reminders() == []
    # Cancelling again (or an unknown id) reports nothing removed.
    assert store.cancel_reminder(r.id) is False
