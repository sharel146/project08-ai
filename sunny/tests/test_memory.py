from sunny.memory import Store


def test_remember_and_recall(tmp_path):
    store = Store(tmp_path / "t.db")
    store.remember("owner prefers tea over coffee", tag="preference")
    store.remember("garage code is on the fridge", tag="note")

    hits = store.recall("tea")
    assert len(hits) == 1
    assert hits[0].tag == "preference"
    assert "tea" in hits[0].text

    assert store.recall("nothing here") == []


def test_recent_orders_newest_first(tmp_path):
    store = Store(tmp_path / "t.db")
    store.remember("first")
    store.remember("second")
    recent = store.recent(limit=2)
    assert [m.text for m in recent] == ["second", "first"]


def test_events_logged(tmp_path):
    store = Store(tmp_path / "t.db")
    store.log_event("test", "something happened")
    events = store.recent_events()
    assert events[0]["kind"] == "test"
    assert events[0]["detail"] == "something happened"
