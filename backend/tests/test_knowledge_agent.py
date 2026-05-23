from io import BytesIO


def _create_case(client):
    response = client.post(
        "/api/cases",
        json={
            "title": "No output linear cavity",
            "description": "Linear cavity has no measurable output after alignment.",
            "cavity_type": "linear",
            "goal": "Recover stable output.",
            "parameters": {"wavelength": "1064 nm", "pump_power": "2 W"},
            "symptoms": ["no output"],
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_case_is_indexed_and_searchable(client):
    case_id = _create_case(client)

    response = client.post("/api/knowledge/search", json={"query": "linear no output pump", "case_id": case_id})

    assert response.status_code == 200
    data = response.json()
    assert data["retrieval_run_id"]
    assert data["results"]
    assert data["results"][0]["source_type"] == "case"


def test_attachment_upload_indexes_text(client):
    case_id = _create_case(client)

    response = client.post(
        f"/api/cases/{case_id}/attachments",
        files={"file": ("notes.txt", BytesIO(b"alignment threshold and thermal lens note"), "text/plain")},
    )
    assert response.status_code == 201

    search = client.post("/api/knowledge/search", json={"query": "thermal lens threshold", "case_id": case_id})

    assert search.status_code == 200
    assert any(result["source_type"] == "attachment" for result in search.json()["results"])


def test_image_upload_can_be_analyzed(client):
    case_id = _create_case(client)

    upload = client.post(
        f"/api/cases/{case_id}/attachments",
        files={"file": ("beam.png", BytesIO(b"fake-png-bytes"), "image/png")},
    )
    assert upload.status_code == 201

    analysis = client.post(f"/api/attachments/{upload.json()['id']}/analyze")

    assert analysis.status_code == 200
    assert analysis.json()["generated_content_id"]
    assert analysis.json()["content"]["attachment_id"] == upload.json()["id"]


def test_generation_returns_citations(client):
    case_id = _create_case(client)

    response = client.post(f"/api/cases/{case_id}/generate-troubleshooting", json={"use_rag": True})

    assert response.status_code == 200
    content = response.json()["content"]
    assert "citations" in content
    assert content["confidence"] in {"medium", "low"}


def test_agent_task_persists_steps_tool_calls_and_artifact(client):
    case_id = _create_case(client)

    response = client.post(
        "/api/agent/tasks",
        json={
            "case_id": case_id,
            "goal": "Analyze why this linear cavity has no output and create a troubleshooting plan.",
            "mode": "troubleshooting",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "completed"
    assert data["final_content_id"]
    assert len(data["steps"]) == 4
    assert any(call["tool_name"] == "search_knowledge" for call in data["tool_calls"])


def test_agent_chat_routes_to_tool_task(client):
    case_id = _create_case(client)

    response = client.post(
        "/api/agent/chat",
        json={"case_id": case_id, "message": "Please create a troubleshooting plan for no output.", "mode": "auto"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["routed_mode"] == "troubleshooting"
    assert data["task"]["status"] == "completed"
    assert data["session_id"]


def test_agent_chat_persists_case_aware_messages(client):
    case_id = _create_case(client)

    response = client.post(
        "/api/agent/chat",
        json={"case_id": case_id, "message": "What should I check first?", "mode": "chat"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["routed_mode"] == "chat"
    assert data["session_id"]

    messages = client.get(f"/api/agent/sessions/{data['session_id']}/messages")
    assert messages.status_code == 200
    payload = messages.json()
    assert [item["role"] for item in payload] == ["user", "assistant"]
    assert "selected case context" in payload[1]["content"] or "current case context" in payload[1]["content"]


def test_global_knowledge_upload_is_used_by_agent_chat(client):
    case_id = _create_case(client)
    upload = client.post(
        "/api/knowledge/sources/upload",
        files={"file": ("lab-sop.txt", BytesIO(b"Lab SOP requires beam dumps before alignment."), "text/plain")},
    )
    assert upload.status_code == 201
    assert upload.json()["case_id"] is None

    response = client.post(
        "/api/agent/chat",
        json={"case_id": case_id, "message": "What does the lab SOP say about beam dumps?", "mode": "chat"},
    )

    assert response.status_code == 200
    citations = response.json()["citations"]
    assert any(citation["source_type"] == "global_attachment" for citation in citations)


def test_agent_chat_provider_failure_returns_bad_gateway(client, monkeypatch):
    case_id = _create_case(client)

    class FailingProvider:
        async def generate_troubleshooting(self, symptoms, case_data):
            raise RuntimeError("provider request was blocked")

    monkeypatch.setattr("app.agent.orchestrator.get_ai_provider", lambda: FailingProvider())

    response = client.post(
        "/api/agent/chat",
        json={"case_id": case_id, "message": "Please create a troubleshooting plan for no output.", "mode": "auto"},
    )

    assert response.status_code == 502
    assert "Failed to generate troubleshooting" in response.json()["detail"]


def test_audit_logs_are_role_protected(client):
    _create_case(client)

    forbidden = client.get("/api/admin/audit-logs")
    assert forbidden.status_code == 403

    allowed = client.get("/api/admin/audit-logs", headers={"x-user-role": "admin"})
    assert allowed.status_code == 200
    assert any(item["action"] == "case.create" for item in allowed.json())
