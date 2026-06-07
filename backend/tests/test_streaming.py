from app.core.streaming import normalize_chat_event


def test_normalize_extension_passthrough() -> None:
    payload = {
        "name": "turn_start",
        "version": "1.0",
        "data": {"turn_index": 1, "intent": "new_topic"},
    }
    out = normalize_chat_event("extension", payload)
    assert out == [("extension", payload)]


def test_normalize_session_extension() -> None:
    out = normalize_chat_event("session", {"session_id": "abc"})
    assert out[0][0] == "extension"
    assert out[0][1]["name"] == "session"
    assert out[0][1]["data"] == {"session_id": "abc"}
