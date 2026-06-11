"""Tests for long-conversation summary and memory management."""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _chat(client, session_id, case_id, message):
    resp = client.post(
        "/api/agent/chat",
        json={
            "session_id": session_id,
            "case_id": case_id,
            "message": message,
            "mode": "chat",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_case(client):
    resp = client.post(
        "/api/cases",
        json={"title": "Memory test case", "cavity_type": "linear", "goal": "debug no output"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Short conversation: no summary should be created
# ---------------------------------------------------------------------------

def test_short_chat_does_not_create_summary(client):
    case_id = _create_case(client)
    session_id = None
    for i in range(4):
        data = _chat(client, session_id, case_id, f"Short message {i}")
        session_id = data["session_id"]

    resp = client.get(f"/api/agent/sessions/{session_id}/summary")
    assert resp.status_code == 200
    assert resp.json()["summary"] is None


# ---------------------------------------------------------------------------
# Long conversation: summary should be created
# ---------------------------------------------------------------------------

def test_long_chat_creates_summary(client):
    case_id = _create_case(client)
    session_id = None
    for i in range(20):
        data = _chat(client, session_id, case_id, f"Message {i}: no output issue detail for long session")
        session_id = data["session_id"]

    resp = client.get(f"/api/agent/sessions/{session_id}/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"], "Expected a non-empty summary after 20 messages"
    assert body["message_count"] > 0


# ---------------------------------------------------------------------------
# Long conversation: memories should be extracted
# ---------------------------------------------------------------------------

def test_long_chat_creates_memories(client):
    case_id = _create_case(client)
    session_id = None
    for i in range(20):
        data = _chat(
            client, session_id, case_id,
            f"Message {i}: no output from the laser, need alignment help"
        )
        session_id = data["session_id"]

    resp = client.get(f"/api/agent/sessions/{session_id}/memories")
    assert resp.status_code == 200
    memories = resp.json()
    assert isinstance(memories, list)
    assert len(memories) > 0, "Expected memory items to be extracted"
    for item in memories:
        assert "content" in item
        assert "memory_type" in item
        assert "importance" in item


# ---------------------------------------------------------------------------
# Session not found → 404
# ---------------------------------------------------------------------------

def test_summary_endpoint_returns_404_for_missing_session(client):
    resp = client.get("/api/agent/sessions/999999/summary")
    assert resp.status_code == 404


def test_memories_endpoint_returns_404_for_missing_session(client):
    resp = client.get("/api/agent/sessions/999999/memories")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Memories endpoint for session with no memories returns empty list
# ---------------------------------------------------------------------------

def test_memories_endpoint_returns_empty_list_for_short_session(client):
    case_id = _create_case(client)
    session_id = None
    for i in range(3):
        data = _chat(client, session_id, case_id, f"Short {i}")
        session_id = data["session_id"]

    resp = client.get(f"/api/agent/sessions/{session_id}/memories")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Summary message_count increases with more messages
# ---------------------------------------------------------------------------

def test_summary_message_count_grows(client):
    case_id = _create_case(client)
    session_id = None
    for i in range(20):
        data = _chat(client, session_id, case_id, f"Turn {i}: laser alignment no output")
        session_id = data["session_id"]

    resp1 = client.get(f"/api/agent/sessions/{session_id}/summary")
    count1 = resp1.json()["message_count"]

    # Add more messages to push another summarise
    for i in range(20, 36):
        _chat(client, session_id, case_id, f"Turn {i}: safety check no output")

    resp2 = client.get(f"/api/agent/sessions/{session_id}/summary")
    count2 = resp2.json()["message_count"]

    assert count2 > count1, "message_count should grow as more turns are summarised"
