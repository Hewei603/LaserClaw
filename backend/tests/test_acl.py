def _admin_headers():
    return {"x-user-role": "admin", "x-user-id": "99", "x-user-email": "admin@example.com"}


def _user_headers(user_id: int):
    return {"x-user-role": "user", "x-user-id": str(user_id), "x-user-email": f"user{user_id}@example.com"}


def _create_user(client, user_id_hint: int):
    response = client.post(
        "/api/collaboration/users",
        headers=_admin_headers(),
        json={
            "email": f"user{user_id_hint}@example.com",
            "display_name": f"User {user_id_hint}",
            "role": "user",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_project_case(client):
    owner_id = _create_user(client, 1)
    outsider_id = _create_user(client, 2)
    project = client.post(
        "/api/collaboration/projects",
        headers=_admin_headers(),
        json={"name": "Restricted project", "visibility": "private"},
    )
    assert project.status_code == 201
    project_id = project.json()["id"]
    member = client.post(
        f"/api/collaboration/projects/{project_id}/members",
        headers=_admin_headers(),
        json={"user_id": owner_id, "role": "viewer"},
    )
    assert member.status_code == 201
    case = client.post(
        "/api/cases",
        headers=_admin_headers(),
        json={
            "project_id": project_id,
            "owner_id": owner_id,
            "title": "Restricted no output cavity",
            "description": "Contains SECRET-ACL-TOKEN for retrieval isolation.",
            "cavity_type": "linear",
            "goal": "Recover output.",
            "visibility": "project",
            "parameters": {"token": "SECRET-ACL-TOKEN"},
            "symptoms": ["no output"],
        },
    )
    assert case.status_code == 201
    return case.json()["id"], owner_id, outsider_id


def test_case_view_requires_acl(client):
    case_id, owner_id, outsider_id = _create_project_case(client)

    allowed = client.get(f"/api/cases/{case_id}", headers=_user_headers(owner_id))
    assert allowed.status_code == 200

    forbidden = client.get(f"/api/cases/{case_id}", headers=_user_headers(outsider_id))
    assert forbidden.status_code == 403


def test_knowledge_search_does_not_leak_inaccessible_case_chunks(client):
    case_id, owner_id, outsider_id = _create_project_case(client)

    owner_search = client.post(
        "/api/knowledge/search",
        headers=_user_headers(owner_id),
        json={"query": "SECRET-ACL-TOKEN", "top_k": 5},
    )
    assert owner_search.status_code == 200
    assert any(result["source_type"] == "case" for result in owner_search.json()["results"])

    outsider_search = client.post(
        "/api/knowledge/search",
        headers=_user_headers(outsider_id),
        json={"query": "SECRET-ACL-TOKEN", "top_k": 5},
    )
    assert outsider_search.status_code == 200
    assert all("SECRET-ACL-TOKEN" not in result["snippet"] for result in outsider_search.json()["results"])

    explicit_forbidden = client.post(
        "/api/knowledge/search",
        headers=_user_headers(outsider_id),
        json={"query": "SECRET-ACL-TOKEN", "case_id": case_id, "top_k": 5},
    )
    assert explicit_forbidden.status_code == 403


def test_agent_task_requires_case_edit_access(client):
    case_id, owner_id, outsider_id = _create_project_case(client)

    forbidden = client.post(
        "/api/agent/tasks",
        headers=_user_headers(outsider_id),
        json={"case_id": case_id, "goal": "Create a troubleshooting plan.", "mode": "troubleshooting"},
    )
    assert forbidden.status_code == 403

    owner_without_editor = client.post(
        "/api/agent/tasks",
        headers=_user_headers(owner_id),
        json={"case_id": case_id, "goal": "Create a troubleshooting plan.", "mode": "troubleshooting"},
    )
    assert owner_without_editor.status_code == 201


def test_case_modules_follow_case_acl(client):
    case_id, owner_id, outsider_id = _create_project_case(client)

    created = client.post(
        f"/api/cases/{case_id}/modules",
        headers=_user_headers(owner_id),
        json={"module_type": "components", "title": "Restricted components"},
    )
    assert created.status_code == 201
    module_id = created.json()["id"]

    forbidden_list = client.get(f"/api/cases/{case_id}/modules", headers=_user_headers(outsider_id))
    assert forbidden_list.status_code == 403

    forbidden_run = client.post(
        f"/api/cases/modules/{module_id}/run",
        headers=_user_headers(outsider_id),
        json={"config_json": {}},
    )
    assert forbidden_run.status_code == 403

    allowed_run = client.post(
        f"/api/cases/modules/{module_id}/run",
        headers=_user_headers(owner_id),
        json={"config_json": {}},
    )
    assert allowed_run.status_code == 200
