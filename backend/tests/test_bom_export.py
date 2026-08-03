"""Full-BOM export vs procurement export.

The teardown deliverable (泵表) is a list where every part is already in the
machine — the procurement CSV's ``owned == False`` filter returns an empty
file for exactly that case. The BOM export must include owned parts, and both
exports must carry a UTF-8 BOM so Excel decodes Chinese cells correctly.
"""

HEADERS = {"x-user-id": "1", "x-user-role": "admin"}


def _make_case_with_parts(client):
    case = client.post("/api/cases", json={
        "title": "40W 飞秒光纤激光器拆解",
        "description": "二手机拆解记录",
        "cavity_type": "linear",
        "goal": "产出泵表",
    }, headers=HEADERS).json()
    parts = [
        {"category": "泵浦", "name": "976nm 泵浦 LD", "specification": "25W 尾纤输出",
         "quantity": 2, "owned": True, "vendor": "厂家A"},
        {"category": "光纤器件", "name": "合束器 (2+1)x1", "specification": "105/125",
         "quantity": 1, "owned": True},
        {"category": "待采购", "name": "替换隔离器", "specification": "1064nm 高功率",
         "quantity": 1, "owned": False},
    ]
    for p in parts:
        resp = client.post(f"/api/cases/{case['id']}/components", json=p, headers=HEADERS)
        assert resp.status_code == 201, resp.text
    return case["id"]


def test_bom_includes_owned_parts(client):
    case_id = _make_case_with_parts(client)
    resp = client.get(f"/api/cases/{case_id}/components/bom.csv", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.text
    # Owned teardown parts are the whole point of this export.
    assert "976nm 泵浦 LD" in body
    assert "合束器 (2+1)x1" in body
    assert "替换隔离器" in body
    assert "类别" in body  # Chinese headers: the deliverable opens in Excel


def test_procurement_still_filters_to_not_owned(client):
    case_id = _make_case_with_parts(client)
    resp = client.get(f"/api/cases/{case_id}/components/procurement.csv", headers=HEADERS)
    assert resp.status_code == 200
    assert "替换隔离器" in resp.text
    assert "976nm 泵浦 LD" not in resp.text


def test_both_exports_carry_utf8_bom_for_excel(client):
    case_id = _make_case_with_parts(client)
    for path in ("bom.csv", "procurement.csv"):
        resp = client.get(f"/api/cases/{case_id}/components/{path}", headers=HEADERS)
        assert resp.text.startswith("\ufeff"), f"{path} lacks the UTF-8 BOM Excel needs for Chinese"


def test_module_run_config_replaces_stored(client):
    """A non-empty run payload must REPLACE the stored config, not merge.

    The module form is pre-filled from the stored config and sends the complete
    effective set; under merge semantics a field the user cleared would win
    back its old value on every re-run, invisibly. An empty payload still
    re-runs with the stored config (the plain "run again" button).
    """
    case_id = _make_case_with_parts(client)
    mod = client.post(f"/api/cases/{case_id}/modules",
                      json={"module_type": "phase_match", "title": "pm"}, headers=HEADERS).json()

    r1 = client.post(f"/api/cases/modules/{mod['id']}/run",
                     json={"config_json": {"crystal": "lbo", "lambda1_nm": 1030, "pm_type": "I"}},
                     headers=HEADERS)
    assert r1.status_code == 200

    r2 = client.post(f"/api/cases/modules/{mod['id']}/run",
                     json={"config_json": {"crystal": "lbo", "lambda1_nm": 1064}},
                     headers=HEADERS)
    assert r2.status_code == 200
    stored = r2.json()["config_json"]
    assert stored["lambda1_nm"] == 1064
    assert "pm_type" not in stored, "cleared field resurrected: run payload was merged, not replaced"

    r3 = client.post(f"/api/cases/modules/{mod['id']}/run", json={"config_json": {}}, headers=HEADERS)
    assert r3.status_code == 200
    assert r3.json()["config_json"]["lambda1_nm"] == 1064
