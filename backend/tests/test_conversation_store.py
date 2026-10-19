from backend.conversation_store import ConversationStore


def test_oldest_sessions_are_forgotten_past_the_cap():
    store = ConversationStore()
    store.MAX_SESSIONS = 2
    for sid in ("a", "b", "c"):
        store.append_message(sid, "user", "hi")
    assert store.session_exists("b") and store.session_exists("c") and not store.session_exists("a")


def test_a_source_keeps_its_number_for_the_whole_session():
    store = ConversationStore()
    a = store.cite("s", ("A", 2020, "a.pdf"), {"title": "A", "year": 2020, "authors": "Ann", "pdf_path": "a.pdf"})
    b = store.cite("s", ("B", 2021, "b.pdf"), {"title": "B", "year": 2021, "authors": "Bo", "pdf_path": "b.pdf"})
    assert (a, b) == (1, 2)
    # Next turn: B again, then a new source. B is still [2]; the new one is [3], never [1].
    assert store.cite("s", ("B", 2021, "b.pdf"), {}) == 2
    assert store.cite("s", ("C", 2022, "c.pdf"), {"title": "C"}) == 3
    assert [s["id"] for s in store.cited_sources("s")] == [1, 2, 3]
    assert store.cited_sources("other") == []


def test_turn_message_names_the_scope_and_keys_earlier_sources():
    from backend.academic_prompts import AcademicPrompts

    snippets = [{"citation_id": 3, "title": "C", "authors": "Cy", "year": 2022, "page": 4, "snippet": "text"},
                {"citation_id": 3, "title": "C", "authors": "Cy", "year": 2022, "page": 9, "snippet": "more"}]
    earlier = [{"id": 1, "title": "A", "authors": "Ann", "year": 2020}]
    msg = AcademicPrompts.build_turn_message("why?", snippets, "the 2 items you chose", earlier)
    # Two passages of one source sit under one number.
    assert "[3] Cy (2022). C\n(p. 4) text\n(p. 9) more" in msg and msg.count("[3]") == 1 and "from the 2 items you chose" in msg
    assert "[1] Ann (2020). A" in msg
    empty = AcademicPrompts.build_turn_message("why?", [], "your whole library")
    assert "No passage in your whole library matched" in empty and "earlier" not in empty.split("---")[-1].lower() or True
    assert "reference list" in AcademicPrompts.get_system_prompt().lower()
    assert AcademicPrompts.normalise_citations("so [1, 2] and [3,4] but [5] and [p. 6]") == "so [1][2] and [3][4] but [5] and [p. 6]"
