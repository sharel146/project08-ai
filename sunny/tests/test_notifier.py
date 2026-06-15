from sunny.notifier import Notifier, build_publish_request


def test_parse_line_message():
    line = '{"event":"message","message":"hi sunny","time":123,"id":"abc"}'
    msg = Notifier._parse_line(line, since=0)
    assert msg is not None
    assert msg.text == "hi sunny"
    assert msg.time == 123
    assert msg.id == "abc"


def test_parse_line_skips_keepalive_and_junk():
    assert Notifier._parse_line('{"event":"keepalive"}', since=0) is None
    assert Notifier._parse_line('{"event":"open"}', since=0) is None
    assert Notifier._parse_line("not json", since=0) is None
    assert Notifier._parse_line("", since=0) is None


def test_build_publish_request_basics():
    url, body, headers = build_publish_request(
        "https://ntfy.sh", "sunny-updates", "hi there", title="Sunny",
        priority="high", tags=["wave", "robot"],
    )
    assert url == "https://ntfy.sh/sunny-updates"
    assert body == b"hi there"
    assert headers["Title"] == "Sunny"
    assert headers["Priority"] == "high"
    assert headers["Tags"] == "wave,robot"


def test_build_publish_request_trims_trailing_slash():
    url, _, _ = build_publish_request("https://ntfy.sh/", "t", "m")
    assert url == "https://ntfy.sh/t"


def test_title_is_latin1_safe():
    # Emoji/non-latin titles must not crash header construction.
    _, _, headers = build_publish_request(
        "https://ntfy.sh", "t", "m", title="Sunny ☀️"
    )
    assert "Title" in headers
    headers["Title"].encode("latin-1")  # would raise if not latin-1 safe
