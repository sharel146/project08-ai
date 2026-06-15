from sunny.server import process_chat


class FakeBrain:
    def __init__(self):
        self.seen = []

    def handle(self, text):
        self.seen.append(text)
        return f"echo: {text}"


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
