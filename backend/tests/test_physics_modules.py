"""Integration tests: physics kernel exposed as case modules and agent tools."""


def _create_case(client, parameters=None):
    response = client.post(
        "/api/cases",
        json={
            "title": "Nd:YAG 1064 intracavity SHG",
            "description": "808 pump, Nd:YAG to 1064, LBO SHG to 532.",
            "cavity_type": "linear",
            "goal": "Design a stable cavity and phase matching.",
            "parameters": parameters or {},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_module(client, case_id, module_type, config=None):
    response = client.post(
        f"/api/cases/{case_id}/modules",
        json={"module_type": module_type, "config_json": config or {}},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --- REST module path -------------------------------------------------------

def test_cavity_design_module_analyze(client):
    case_id = _create_case(client)
    module_id = _create_module(client, case_id, "cavity_design", {
        "wavelength_nm": 1064, "R1_mm": "flat", "R2_mm": 500, "L_mm": 350,
        "crystal": {"n": 1.8147, "thickness_mm": 10, "position_mm": 20},
    })
    run = client.post(f"/api/cases/modules/{module_id}/run", json={"config_json": {}})
    assert run.status_code == 200, run.text
    result = run.json()["result_json"]
    assert result["status"] == "completed"
    assert result["analysis"]["stable"] is True
    assert result["analysis"]["waist_w0_mm"] > 0
    assert any(p["element"] == "Crystal entrance" for p in result["placement"])


def test_cavity_design_module_scan_recommends_length(client):
    case_id = _create_case(client)
    module_id = _create_module(client, case_id, "cavity_design", {
        "wavelength_nm": 1064, "R1_mm": "flat", "R2_mm": 500,
        "L_scan_mm": {"start": 100, "stop": 600, "step": 25},
        "target_waist_mm": 0.25,
    })
    run = client.post(f"/api/cases/modules/{module_id}/run", json={"config_json": {}})
    result = run.json()["result_json"]
    assert result["status"] == "completed"
    assert result["scan"]["stable_windows_mm"], "expected at least one stable window"
    assert result["recommended"]["stable"] is True
    assert abs(result["recommended"]["waist_w0_mm"] - 0.25) < 0.05


def test_phase_match_module(client):
    case_id = _create_case(client)
    module_id = _create_module(client, case_id, "phase_match", {
        "crystal": "bbo", "lambda1_nm": 1064, "pm_type": "I",
    })
    run = client.post(f"/api/cases/modules/{module_id}/run", json={"config_json": {}})
    result = run.json()["result_json"]
    assert result["status"] == "completed"
    sol = result["solutions"][0]
    assert abs(sol["theta_deg"] - 22.8) < 0.5


def test_coating_tmm_module_nominal(client):
    case_id = _create_case(client)
    module_id = _create_module(client, case_id, "coating_tmm", {
        "nominal": {"function": "HR", "design_wavelength_nm": 1123},
        "query_wavelengths_nm": [1064],
    })
    run = client.post(f"/api/cases/modules/{module_id}/run", json={"config_json": {}})
    result = run.json()["result_json"]
    assert result["status"] == "completed"
    assert result["mode_used"] == "archetype"
    assert result["recommend_measurement"] is True


def test_module_config_falls_back_to_case_parameters(client):
    # cavity parameters live on the case; the module carries no config of its own
    case_id = _create_case(client, parameters={
        "wavelength_nm": 1064, "R1_mm": "flat", "R2_mm": 400, "L_mm": 300,
    })
    module_id = _create_module(client, case_id, "cavity_design")
    run = client.post(f"/api/cases/modules/{module_id}/run", json={"config_json": {}})
    result = run.json()["result_json"]
    assert result["status"] == "completed"
    assert result["analysis"]["stable"] is True


# --- Agent task path --------------------------------------------------------

def test_agent_task_executes_cavity_design_tool(client):
    case_id = _create_case(client, parameters={
        "wavelength_nm": 1064, "R1_mm": "flat", "R2_mm": 500,
        "L_scan_mm": {"start": 100, "stop": 600, "step": 50},
        "target_waist_mm": 0.25,
    })
    task = client.post(
        "/api/agent/tasks",
        json={"case_id": case_id, "goal": "设计谐振腔并给出腔长与束腰", "mode": "cavity_design"},
    )
    assert task.status_code == 201, task.text
    body = task.json()
    assert body["status"] == "completed"
    tool_names = [c["tool_name"] for c in body["tool_calls"]]
    assert "compute_cavity_design" in tool_names
    assert "search_knowledge" in tool_names
    compute = next(c for c in body["tool_calls"] if c["tool_name"] == "compute_cavity_design")
    assert compute["status"] == "completed"
    assert compute["output_json"]["recommended"]["stable"] is True


def test_agent_task_executes_phase_match_tool(client):
    case_id = _create_case(client, parameters={"crystal": "lbo", "lambda1_nm": 1064, "pm_type": "I"})
    task = client.post(
        "/api/agent/tasks",
        json={"case_id": case_id, "goal": "计算LBO倍频相位匹配角", "mode": "phase_match"},
    )
    assert task.status_code == 201, task.text
    body = task.json()
    compute = next(c for c in body["tool_calls"] if c["tool_name"] == "compute_phase_match")
    matched = [s for s in compute["output_json"]["solutions"] if s["theta_deg"] is not None]
    assert matched, "LBO SHG 1064 must phase-match"


# --- Chat routing -----------------------------------------------------------

def test_chat_routes_cavity_design(client):
    case_id = _create_case(client, parameters={
        "wavelength_nm": 1064, "R1_mm": "flat", "R2_mm": 500, "L_mm": 350,
    })
    response = client.post(
        "/api/agent/chat",
        json={"case_id": case_id, "message": "帮我设计一个谐振腔，算一下腔长和束腰"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["routed_mode"] == "cavity_design"


def test_chat_routes_phase_match(client):
    case_id = _create_case(client)
    response = client.post(
        "/api/agent/chat",
        json={"case_id": case_id, "message": "帮我计算LBO的相位匹配角"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["routed_mode"] == "phase_match"


def test_chat_without_intent_stays_chat(client):
    case_id = _create_case(client)
    response = client.post(
        "/api/agent/chat",
        json={"case_id": case_id, "message": "谐振腔是什么原理？"},
    )
    assert response.status_code == 200
    assert response.json()["routed_mode"] == "chat"
