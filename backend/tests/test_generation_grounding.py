"""The provider must receive the same evidence that the saved draft cites."""
import copy

import pytest

from app.models import CaseModule, KnowledgeSource, RetrievalRun, ExperimentCase, GeneratedContent


@pytest.mark.parametrize("mode", ["plan", "troubleshooting", "report"])
def test_generation_receives_evidence_and_recorded_results(client, db, monkeypatch, mode):
    case = client.post("/api/cases", json={
        "title": "Grounding review", "cavity_type": "linear", "goal": "Grounding review",
        "measurements": {"output_power_W": 9.876}, "conclusions": "Recorded test conclusion",
        "safety_notes": "Recorded lab instruction",
    }).json()
    db.add(CaseModule(case_id=case["id"], module_type="power_curve", title="Measured curve",
                      status="completed", result_json={"measured_marker": "MODULE_582"}))
    db.commit()
    source = client.post("/api/knowledge/sources/upload", files={
        "file": ("grounding.txt", b"Grounding review. Mandatory lab evidence: EVIDENCE_973.", "text/plain"),
    }).json()
    received = []

    async def generate(*args):
        received.append(copy.deepcopy(args[-1]))
        assert db.query(RetrievalRun).count() == 1, "retrieval must precede the provider"
        return {"title": "Draft", "missing_information": ["Need measured jitter"]}

    provider = type("SpyProvider", (), {})()
    setattr(provider, f"generate_{mode}", generate)
    monkeypatch.setattr("app.api.generation.get_ai_provider", lambda: provider)
    response = client.post(f"/api/cases/{case['id']}/generate-{mode}", json={"use_rag": True, "top_k": 5})
    assert response.status_code == 200, response.text
    payload = received[0]
    assert payload["measurements"]["output_power_W"] == 9.876
    assert payload["conclusions"] == "Recorded test conclusion"
    assert payload["safety_notes"] == "Recorded lab instruction"
    assert payload["module_results"][0]["result"]["measured_marker"] == "MODULE_582"
    assert any("EVIDENCE_973" in hit["snippet"] for hit in payload["retrieved_knowledge"])
    content = response.json()["content"]
    assert content["citations"] == payload["retrieval_context"]["citations"]
    assert any(c["source_id"] == source["id"] for c in content["citations"])
    assert db.query(RetrievalRun).count() == 1, "do not run a second search after generating"


def test_generation_can_disable_retrieval(client, monkeypatch):
    cid = client.post("/api/cases", json={"title": "No RAG", "cavity_type": "linear", "goal": "Test"}).json()["id"]

    def forbidden(*args, **kwargs):
        raise AssertionError("use_rag=false must not search")

    monkeypatch.setattr("app.api.generation.search_case_and_global_knowledge", forbidden)
    response = client.post(f"/api/cases/{cid}/generate-report", json={"use_rag": False})
    assert response.status_code == 200, response.text
    assert "retrieval" not in response.json()["content"]


def test_missing_evidence_reaches_model_and_preserves_other_missing_inputs(client, db, monkeypatch):
    cid = client.post("/api/cases", json={"title": "No evidence", "cavity_type": "linear", "goal": "Test"}).json()["id"]
    for source in db.query(KnowledgeSource).all():
        source.governance_status = "archived"
    db.commit()

    class SpyProvider:
        async def generate_report(self, payload):
            assert payload["retrieval_context"]["retrieval"]["no_answer"] is True
            assert payload["retrieved_knowledge"] == []
            return {"missing_information": ["Need measured jitter"]}

    monkeypatch.setattr("app.api.generation.get_ai_provider", SpyProvider)
    response = client.post(f"/api/cases/{cid}/generate-report")
    assert response.status_code == 200, response.text
    content = response.json()["content"]
    assert content["missing_information"][0] == "Need measured jitter"
    assert len(content["missing_information"]) == 2
    assert content["retrieval"]["no_answer"] is True


@pytest.mark.parametrize("mode", ["plan", "report", "troubleshooting"])
def test_new_project_supersedes_old_geometry_in_generation(client, db, monkeypatch, mode):
    from app.workbench.projects import SaveProject, save_project

    case = client.post("/api/cases", json={
        "title": "用户更正晶体尺寸", "parameters": {"R1_mm": "flat", "R2_mm": 300, "L_mm": 39},
    }).json()
    old = GeneratedContent(case_id=case["id"], content_type="plan",
                           content={"engineering_design": {"old_crystal_mm": 17}})
    db.add(old)
    db.commit()
    saved = save_project(db, case["id"], SaveProject.model_validate({
        "project": {"title": "当前11mm晶体", "system": {"mode": "standing_wave", "wavelength_nm": 1064,
            "elements": [{"name": "M1", "kind": "mirror", "radius_mm": 200},
                         {"name": "front", "kind": "space", "length_mm": 3},
                         {"name": "crystal", "kind": "space", "length_mm": 11, "n": 2.165},
                         {"name": "rear", "kind": "space", "length_mm": 12},
                         {"name": "M2", "kind": "mirror"}]},
            "assumptions": ["无热透镜"], "parts": []}, "change_note": "用户总长改为11mm",
    }))
    db.add(GeneratedContent(case_id=case["id"], content_type="workbench", content={
        "workbench": {"status": "partial", "summary": "几何已计算，功率效率仍待实测。"},
    }))
    db.commit()

    async def generate(*args):
        payload = args[-1]
        assert payload["geometry_source"] == "optical_project"
        assert payload["engineering_design"] is None
        assert payload["historical_design_revision_id"] == old.id
        assert payload["latest_workbench_result"]["status"] == "partial"
        current = payload["optical_project"]
        assert current["revision_id"] == saved["revision_id"]
        assert current["project"]["system"]["elements"][2]["length_mm"] == 11
        assert "samples" not in current["analysis"]["planes"]["tangential"]
        if mode == "plan":
            assert payload["computed_physics"]["project_revision_id"] == saved["revision_id"]
        return {"title": "当前工程报告"}

    provider = type("SpyProvider", (), {})()
    setattr(provider, f"generate_{mode}", generate)
    monkeypatch.setattr("app.api.generation.get_ai_provider", lambda: provider)
    monkeypatch.setattr("app.api.generation.compute_case_physics",
                        lambda *a, **kw: pytest.fail("Must not recompute superseded case geometry"))
    response = client.post(f"/api/cases/{case['id']}/generate-{mode}", json={"use_rag": False})
    assert response.status_code == 200, response.text
    assert db.get(ExperimentCase, case["id"]).parameters["L_mm"] == 39  # provenance retained
