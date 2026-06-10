"""Tests for V1.2 case module workflows."""


def _case_payload():
    return {
        "title": "V1.2 module case",
        "description": "Case for optional module tests",
        "cavity_type": "linear",
        "goal": "Build a stable laser test workflow",
        "parameters": {"gain_medium": "Nd:YAG"},
        "symptoms": [],
    }


def test_component_module_generation_and_procurement_export(client):
    case_response = client.post("/api/cases", json=_case_payload())
    assert case_response.status_code == 201
    case_id = case_response.json()["id"]

    module_response = client.post(
        f"/api/cases/{case_id}/modules",
        json={"module_type": "components", "title": "Case procurement"},
    )
    assert module_response.status_code == 201
    module_id = module_response.json()["id"]

    run_response = client.post(f"/api/cases/modules/{module_id}/run", json={"config_json": {}})
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "completed"

    items_response = client.get(f"/api/cases/{case_id}/components")
    assert items_response.status_code == 200
    items = items_response.json()
    assert len(items) >= 5
    assert any(item["name"] == "Power meter" for item in items)

    export_response = client.get(f"/api/cases/{case_id}/components/procurement.csv")
    assert export_response.status_code == 200
    assert "Power meter" in export_response.text
