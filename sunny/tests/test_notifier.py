from sunny.notifier import build_publish_request


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
