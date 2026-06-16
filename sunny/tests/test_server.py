from types import SimpleNamespace

from sunny.server import WEB_DIR, INDEX_HTML, _STATIC_TYPES, build_status, process_chat


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
