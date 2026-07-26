"""Phase two collaboration and governance API tests."""


# Bootstrap identities use high, non-colliding ids that no test provisions, so
# they stay on the "unknown user -> header role" bootstrap path. A provisioned
# user (ids start at 1) can no longer borrow these roles by header alone.
ADMIN_HEADERS = {"X-User-Role": "admin", "X-User-Email": "admin@example.test", "X-User-Id": "99"}
REVIEWER_HEADERS = {"X-User-Role": "reviewer", "X-User-Email": "reviewer@example.test", "X-User-Id": "98"}


def test_project_case_v2_and_bundle_export(client):
    user = client.post(
        "/api/collaboration/users",
        json={"email": "owner@example.test", "display_name": "Owner", "role": "admin"},
        headers=ADMIN_HEADERS,
    )
    assert user.status_code == 201
    project = client.post(
        "/api/collaboration/projects",
        json={"name": "Long term laser project", "visibility": "organization"},
        headers=ADMIN_HEADERS,
    )
    assert project.status_code == 201

    case = client.post(
        "/api/cases",
        json={
            "project_id": project.json()["id"],
            "title": "Phase two case",
            "cavity_type": "linear",
            "goal": "Track a collaborative experiment",
            "status": "active",
            "tags": ["nd:yag", "alignment"],
            "measurements": {"power_w": 4.2},
            "safety_notes": "Class 4 controls verified.",
        },
        headers={"X-User-Id": str(user.json()["id"])},
    )
    assert case.status_code == 201
    body = case.json()
    assert body["schema_version"] == "case_v2"
    assert body["project_id"] == project.json()["id"]
    assert body["measurements"]["power_w"] == 4.2

    bundle = client.get(f"/api/cases/{body['id']}/bundle")
    assert bundle.status_code == 200
    assert bundle.headers["content-type"] == "application/zip"


def test_group_and_project_memberships(client):
    user = client.post(
        "/api/collaboration/users",
        json={"email": "member@example.test", "display_name": "Member"},
        headers=ADMIN_HEADERS,
    )
    group = client.post("/api/collaboration/groups", json={"name": "Optics team"}, headers=ADMIN_HEADERS)
    project = client.post("/api/collaboration/projects", json={"name": "Shared project"}, headers=ADMIN_HEADERS)
    assert user.status_code == 201
    assert group.status_code == 201
    assert project.status_code == 201

    group_member = client.post(
        f"/api/collaboration/groups/{group.json()['id']}/members",
        json={"user_id": user.json()["id"], "role": "member"},
        headers=ADMIN_HEADERS,
    )
    assert group_member.status_code == 201

    project_member = client.post(
        f"/api/collaboration/projects/{project.json()['id']}/members",
        json={"group_id": group.json()["id"], "role": "editor"},
        headers=ADMIN_HEADERS,
    )
    assert project_member.status_code == 201
    assert project_member.json()["role"] == "editor"


def test_knowledge_governance_and_rag_eval(client):
    case = client.post("/api/cases", json={"title": "KB case", "cavity_type": "ring", "goal": "Stabilize output"})
    assert case.status_code == 201
    sources = client.get(f"/api/knowledge/sources?case_id={case.json()['id']}")
    assert sources.status_code == 200
    source_id = sources.json()[0]["id"]

    reviewed = client.patch(
        f"/api/knowledge/sources/{source_id}/governance",
        json={"governance_status": "approved", "note": "Reviewed for benchmark"},
        headers=REVIEWER_HEADERS,
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["governance_status"] == "approved"

    eval_response = client.post(
        "/api/evals/rag",
        json={
            "name": "smoke benchmark",
            "dataset": [{"query": "Stabilize output", "expected_source_ids": [source_id]}],
        },
    )
    assert eval_response.status_code == 200
    assert eval_response.json()["total_questions"] == 1
    assert eval_response.json()["hit_rate"] == 1.0


def test_prompt_and_workflow_version_activation(client):
    first = client.post(
        "/api/versioning/prompts",
        json={"name": "plan", "version": "v1", "content": "Plan prompt", "is_active": True},
        headers=REVIEWER_HEADERS,
    )
    second = client.post(
        "/api/versioning/prompts",
        json={"name": "plan", "version": "v2", "content": "Plan prompt v2", "is_active": True},
        headers=REVIEWER_HEADERS,
    )
    assert first.status_code == 201
    assert second.status_code == 201
    active_prompts = client.get("/api/versioning/prompts?name=plan&active=true").json()
    assert len(active_prompts) == 1
    assert active_prompts[0]["version"] == "v2"

    workflow = client.post(
        "/api/versioning/workflows",
        json={"name": "troubleshooting", "version": "v1", "definition": {"steps": ["retrieve", "answer"]}},
        headers=REVIEWER_HEADERS,
    )
    assert workflow.status_code == 201
    activated = client.post(f"/api/versioning/workflows/{workflow.json()['id']}/activate", headers=REVIEWER_HEADERS)
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True
