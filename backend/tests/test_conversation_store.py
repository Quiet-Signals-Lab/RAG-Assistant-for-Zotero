from backend.conversation_store import ConversationStore


def test_oldest_sessions_are_forgotten_past_the_cap():
    store = ConversationStore()
    store.MAX_SESSIONS = 2
    for sid in ("a", "b", "c"):
        store.append_message(sid, "user", "hi")
    assert store.session_exists("b") and store.session_exists("c") and not store.session_exists("a")
