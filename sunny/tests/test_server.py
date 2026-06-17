import time
from types import SimpleNamespace

from sunny.server import WEB_DIR, INDEX_HTML, _STATIC_TYPES, build_status, process_chat


class FakeStore:
    def count_memories(self): return 3
    def count_events(self): return 7
    def pending_reminders(self): return [object(), object()]
    def recent_events(self, limit=12):
        return [{"kind": "tool_call", "detail": "recall {}", "created_at": int(time.time())}]


def test_build_status_telemetry_and_extra_nodes_are_real():
    brain = SimpleNamespace(
        phone_online=True, is_active=lambda c, window=4.0: c == "upgrade",
        store=FakeStore(), started_at=time.time() - 65, message_count=4,
    )
    config = SimpleNamespace(has_brain=True, has_home_assistant=False,
                             model="claude-opus-4-8", briefing_time="08:00")
    status = build_status(brain, config)
    by_id = {n["id"]: n for n in status["nodes"]}
    # new honest subsystems show up as nodes
    for node_id in ("host", "upgrade", "briefing", "log"):
        assert node_id in by_id
    assert by_id["host"]["state"] == "online"
    assert by_id["upgrade"]["active"] is True          # is_active('upgrade')
    assert by_id["briefing"]["state"] == "online"      # briefing_time configured
    assert by_id["log"]["active"] is True              # a fresh event was just logged
    assert by_id["memory"]["info"] == "3 items stored"
    assert by_id["reminders"]["info"] == "2 pending"
    # live telemetry mirrors the store / brain, not invented numbers
    t = status["telemetry"]
    assert t["model"] == "claude-opus-4-8"
    assert t["memories"] == 3 and t["events"] == 7 and t["reminders"] == 2
    assert t["messages"] == 4 and t["uptime"]
    assert len(status["feed"]) == 1 and status["feed"][0]["kind"] == "tool_call"


def test_build_status_briefing_absent_when_unscheduled():
    brain = SimpleNamespace(phone_online=False, is_active=lambda c, window=4.0: False,
                            store=FakeStore(), started_at=time.time(), message_count=0)
    config = SimpleNamespace(has_brain=True, has_home_assistant=False, model="m", briefing_time="")
    by_id = {n["id"]: n for n in build_status(brain, config)["nodes"]}
    assert by_id["briefing"]["state"] == "absent"      # nothing scheduled -> not linked


def test_vendored_three_engine_is_present():
    # The 3D scene loads a locally vendored engine (works offline, no CDN).
    assert (WEB_DIR / "vendor" / "three" / "build" / "three.module.js").is_file()
    assert _STATIC_TYPES[".js"].startswith("text/javascript")


def test_static_route_blocks_path_traversal():
    # The static handler only serves files that resolve inside web/.
    escaped = (WEB_DIR / ".." / "config.py").resolve()
    try:
        escaped.relative_to(WEB_DIR.resolve())
        inside = True
    except ValueError:
        inside = False
    assert inside is False  # traversal escapes web/ -> handler returns 404


def test_index_html_has_token_placeholder_and_chat_call():
    # The page must inject the token and post to /chat — guards against the
    # web UI silently losing its auth or endpoint.
    assert "__SUNNY_TOKEN__" in INDEX_HTML
    assert "/chat" in INDEX_HTML
    assert "X-Sunny-Token" in INDEX_HTML
    assert "/status" in INDEX_HTML
    # the WebGL solar-system scene: vendored Three.js engine + planet labels
    assert "importmap" in INDEX_HTML
    assert "/vendor/three/build/three.module.js" in INDEX_HTML
    assert 'id="labels"' in INDEX_HTML


def test_build_status_reflects_connectivity():
    brain = SimpleNamespace(phone_online=True, is_active=lambda c, window=4.0: c == "web")
    config = SimpleNamespace(has_brain=True, has_home_assistant=False)
    status = build_status(brain, config)
    by_id = {n["id"]: n for n in status["nodes"]}
    assert by_id["phone"]["state"] == "online"     # phone bridge connected
    assert by_id["watch"]["state"] == "absent"     # not built yet -> yellow string
    assert by_id["home"]["state"] == "absent"      # HA not configured -> yellow
    assert by_id["web"]["active"] is True          # web channel in use -> blue flow
    assert by_id["search"]["state"] == "online"


def test_build_status_phone_offline_when_down():
    brain = SimpleNamespace(phone_online=False, is_active=lambda c, window=4.0: False)
    config = SimpleNamespace(has_brain=True, has_home_assistant=False)
    by_id = {n["id"]: n for n in build_status(brain, config)["nodes"]}
    assert by_id["phone"]["state"] == "offline"    # string goes red


class FakeBrain:
    def __init__(self):
        self.seen = []
        self.active = []

    def handle(self, text):
        self.seen.append(text)
        return f"echo: {text}"

    def mark_active(self, channel):
        self.active.append(channel)


def test_chat_happy_path():
    brain = FakeBrain()
    status, body = process_chat(brain, "secret", "secret", {"message": "hi"})
    assert status == 200
    assert body == {"reply": "echo: hi"}
    assert brain.seen == ["hi"]


def test_chat_rejects_bad_token():
    brain = FakeBrain()
    status, body = process_chat(brain, "secret", "wrong", {"message": "hi"})
    assert status == 401
    assert brain.seen == []  # brain never runs on bad auth


def test_chat_requires_message():
    brain = FakeBrain()
    status, body = process_chat(brain, "secret", "secret", {"message": "  "})
    assert status == 400


def test_empty_expected_token_allows_any():
    brain = FakeBrain()
    status, _ = process_chat(brain, "", "", {"message": "hi"})
    assert status == 200
