"""Regression tests for authorization hardening.

These cover the two classes of holes fixed together:
  * privilege is resolved from the persisted ``User`` record, so a provisioned
    account cannot escalate itself by forging an ``X-User-Role`` header;
  * ``/api/evals/rag`` requires reviewer/admin and scopes retrieval to the
    caller's accessible cases, so it cannot be used as a content oracle.
"""

# Bootstrap identities: high ids that no test provisions, so they stay on the
# "unknown user -> header role" bootstrap path (demo mode, REQUIRE_AUTH off).
ADMIN_HEADERS = {"x-user-role": "admin", "x-user-id": "99", "x-user-email": "admin@example.com"}
REVIEWER_HEADERS = {"x-user-role": "reviewer", "x-user-id": "98", "x-user-email": "reviewer@example.com"}


def _create_user(client, email, role="user"):
    response = client.post(
        "/api/collaboration/users",
        headers=ADMIN_HEADERS,
        json={"email": email, "display_name": email, "role": role},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_private_case_with_secret(client):
    owner_id = _create_user(client, "owner@example.com")
    project = client.post(
        "/api/collaboration/projects",
        headers=ADMIN_HEADERS,
        json={"name": "Restricted project", "visibility": "private"},
    )
    project_id = project.json()["id"]
    client.post(
        f"/api/collaboration/projects/{project_id}/members",
        headers=ADMIN_HEADERS,
        json={"user_id": owner_id, "role": "viewer"},
    )
    case = client.post(
        "/api/cases",
        headers=ADMIN_HEADERS,
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
    assert case.status_code == 201, case.text
    return case.json()["id"], owner_id


def test_provisioned_user_cannot_escalate_role_via_header(client):
    """A user stored with role 'user' stays a user even if they claim admin."""
    eve_id = _create_user(client, "eve@example.com", role="user")

    forged = {"x-user-role": "admin", "x-user-id": str(eve_id), "x-user-email": "eve@example.com"}
    attempt = client.post(
        "/api/collaboration/users",
        headers=forged,
        json={"email": "puppet@example.com", "display_name": "Puppet", "role": "user"},
    )
    assert attempt.status_code == 403


def test_admin_role_from_db_is_honored(client):
    """A user stored with role 'admin' keeps admin even without an admin header."""
    admin_id = _create_user(client, "realadmin@example.com", role="admin")

    plain = {"x-user-role": "user", "x-user-id": str(admin_id), "x-user-email": "realadmin@example.com"}
    created = client.post(
        "/api/collaboration/groups",
        headers=plain,
        json={"name": "Db-admin team"},
    )
    assert created.status_code == 201


def test_rag_eval_requires_reviewer_or_admin(client):
    """A plain provisioned user may not run the retrieval benchmark."""
    eve_id = _create_user(client, "eve@example.com", role="user")

    response = client.post(
        "/api/evals/rag",
        headers={"x-user-id": str(eve_id), "x-user-role": "user"},
        json={"name": "probe", "dataset": [{"query": "anything"}]},
    )
    assert response.status_code == 403


def test_rag_eval_does_not_leak_inaccessible_case_content(client):
    """A reviewer with no access to a private case cannot probe its content."""
    case_id, _owner_id = _create_private_case_with_secret(client)

    # The reviewer is not a member of the restricted project.
    response = client.post(
        "/api/evals/rag",
        headers=REVIEWER_HEADERS,
        json={
            "name": "oracle probe",
            "dataset": [
                {
                    "query": "SECRET-ACL-TOKEN",
                    "expected_terms": ["SECRET-ACL-TOKEN"],
                    "expected_source_ids": [],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # The private chunk is filtered out of retrieval before scoring: nothing is
    # retrieved, so no term/source hits and no source ids leak back. (The query
    # string the caller supplied is echoed verbatim; that is their own input.)
    assert body["hit_rate"] == 0.0
    for row in body["results"]["rows"]:
        assert row["term_hit"] is False
        assert row["source_hit"] is False
        assert row["source_ids"] == []
        assert row["max_score"] == 0.0

    # A control: a reviewer who *is* granted access retrieves the same content.
    grant = client.post(
        "/api/evals/rag",
        headers=ADMIN_HEADERS,
        json={
            "name": "authorized probe",
            "dataset": [{"query": "SECRET-ACL-TOKEN", "expected_terms": ["SECRET-ACL-TOKEN"]}],
        },
    )
    assert grant.status_code == 200, grant.text
    assert grant.json()["hit_rate"] == 1.0


def test_failed_agent_task_rolls_back_partial_writes(client, monkeypatch):
    """A provider failure must not commit half-built artifacts; the task is
    recorded as 'failed' and no generated content is persisted."""
    case = client.post(
        "/api/cases",
        json={"title": "Rollback case", "cavity_type": "linear", "goal": "no output"},
    )
    assert case.status_code == 201, case.text
    case_id = case.json()["id"]

    class FailingProvider:
        async def generate_troubleshooting(self, symptoms, case_data):
            raise RuntimeError("provider request was blocked")

    monkeypatch.setattr("app.agent.orchestrator.get_ai_provider", lambda: FailingProvider())

    response = client.post(
        "/api/agent/tasks",
        json={"case_id": case_id, "goal": "diagnose no output", "mode": "troubleshooting"},
    )
    assert response.status_code == 502

    tasks = client.get(f"/api/agent/tasks?case_id={case_id}")
    assert tasks.status_code == 200
    statuses = [t["status"] for t in tasks.json()]
    assert statuses == ["failed"]

    # No partially generated artifact leaked from the failed run.
    contents = client.get(f"/api/cases/{case_id}/generated-contents")
    assert contents.status_code == 200
    assert contents.json() == []
