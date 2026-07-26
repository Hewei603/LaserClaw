"""L0 structured inventory + L1 evaluator: parser, importer, API, agent path."""
import io

from app.inventory.parser import classify_category, parse_coating, parse_geometry

REVIEWER = {"x-user-role": "reviewer", "x-user-id": "98", "x-user-email": "rev@example.com"}


# --- parser (grammar from the real workbook) --------------------------------

def test_parse_raman_output_coupler():
    p = parse_coating("S1:1064-1066HR, 1176-1180 T=20%", "S1")
    assert p.confidence == "parsed"
    assert len(p.bands) == 2
    hr = next(b for b in p.bands if b.function == "HR")
    assert (hr.wl_min_nm, hr.wl_max_nm) == (1064.0, 1066.0)
    pr = next(b for b in p.bands if b.function == "PR")
    assert pr.value_type == "T" and pr.value_pct == 20.0


def test_parse_dual_function_surface_with_thresholds():
    p = parse_coating("S1(凹):1064HT T>90% 1076HR R>99.5%", "S1")
    ht = next(b for b in p.bands if b.function == "HT")
    hr = next(b for b in p.bands if b.function == "HR")
    assert ht.wl_min_nm == 1064.0 and ht.value_pct == 90.0 and ht.comparator == ">"
    assert hr.wl_min_nm == 1076.0 and hr.value_pct == 99.5


def test_parse_fullwidth_and_multiwavelength():
    p = parse_coating("S1：HR＠1123（R＞99.5%）＆HT@808+946+1064nm", "S1")
    hr = next(b for b in p.bands if b.function == "HR")
    assert hr.wl_min_nm == 1123.0 and hr.value_pct == 99.5     # full-width Ｒ＞ parsed
    ht_wls = sorted(b.wl_min_nm for b in p.bands if b.function == "HT")
    assert ht_wls == [808.0, 946.0, 1064.0]


def test_parse_bare_wavelengths_adopt_following_function():
    p = parse_coating("S1:1176-1180HR 1064 808 885HT", "S1")
    ht_wls = sorted(b.wl_min_nm for b in p.bands if b.function == "HT")
    assert ht_wls == [808.0, 885.0, 1064.0]


def test_parse_unknown_markers_flag_review():
    p = parse_coating("不能确定是否镀膜", "S1")
    assert p.confidence == "needs_review"
    assert not p.bands


def test_parse_geometry_crystal():
    g = parse_geometry("3*3*5mm3，c-cut，掺杂浓度5at.%", "θ=159.6°")
    assert g.dimensions == "3*3*5mm3"
    assert g.cut_axis == "c-cut"
    assert g.doping_pct == 5.0
    assert g.cut_angle_theta_deg == 159.6


def test_classify_categories():
    assert classify_category("1.1μm拉曼输出镜") == "mirror"
    assert classify_category("Yb:CALGO激光晶体") == "gain_crystal"
    assert classify_category("LBO倍频晶体") == "nonlinear_crystal"


# --- importer + API ---------------------------------------------------------

def _make_workbook_bytes() -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.append(["序号", "物料名称", "镀膜S1", "镀膜S2", "规格", "焦距或曲率半径", "数量", "存放地", "保管人", "厂商"])
    ws1.append([1, "1064腔镜", "S1:1064-1066HR R>99.5%", "S2:1064AR", "D=25.4mm", "R=-400", 2, "127", "张三", "厂商A"])
    ws1.append([2, "", "S1:1064-1066HR R>99.5%", "S2:1064AR", "", "R=-100", 1, "127", "张三", ""])   # forward-fill
    ws1.append([3, "输入镜", "S1：HR＠1123＆HT@808+1064nm", "", "D=25.4mm", "平镜", 1, "127", "李四", ""])
    ws1.append([4, "神秘镜", "不能确定是否镀膜", "", "", "R=-200", 1, "127", "李四", ""])
    ws2 = wb.create_sheet("crystals")
    ws2.append(["Nd：YAG晶体", "S1：AR@808/1123nm", "S2：AR@808/1123nm", "4*4*10 掺杂浓度1.0at.%", None, 4, "127", "王五", "福晶"])
    ws2.append(["LBO倍频晶体", "S1：AR@1123/561nm", "", "3*3*13", None, 3, "127", "王五", "福晶"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_import_and_query_inventory(client):
    resp = client.post(
        "/api/inventory/import",
        files={"file": ("test_inv.xlsx", _make_workbook_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=REVIEWER,
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert report["imported"] == 6
    assert report["coating_bands"] >= 8
    assert report["needs_review"] == 1          # 神秘镜
    assert report["review_queue"]

    # typed SQL filter: mirrors that are HR at 1064
    items = client.get("/api/inventory/items?category=mirror&wavelength_nm=1064&function=HR").json()
    names = {i["name"] for i in items}
    assert "1064腔镜" in names
    assert "神秘镜" not in names

    # forward-filled group name and diameter survived
    cavity = [i for i in items if i["name"] == "1064腔镜"]
    assert len(cavity) == 2
    assert any(i["roc_mm"] == 400.0 for i in cavity)


def test_import_requires_reviewer(client):
    resp = client.post(
        "/api/inventory/import",
        files={"file": ("x.xlsx", b"zz", "application/octet-stream")},
        headers={"x-user-role": "user", "x-user-id": "55"},
    )
    assert resp.status_code == 403


# --- L1 evaluator through the API ------------------------------------------

def _import_inventory(client):
    resp = client.post(
        "/api/inventory/import",
        files={"file": ("test_inv.xlsx", _make_workbook_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=REVIEWER,
    )
    assert resp.status_code == 200


def test_match_finds_design_match_and_rejects_wrong_roc(client):
    _import_inventory(client)
    resp = client.post("/api/inventory/match", json={
        "role": "cavity output coupler",
        "category": "mirror",
        "surfaces": [{"wavelength_nm": 1064, "function": "HR", "min_R_pct": 99.0}],
        "roc_mm": 400,
        "min_diameter_mm": 20,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["eligible_count"] >= 1
    top = body["candidates"][0]
    assert top["name"] == "1064腔镜"
    coat = top["parameters"]["coatings"][0]
    assert coat["status"] == "design_match"
    assert coat["threshold_ok"] is True                      # R>99.5 >= 99.0
    assert top["parameters"]["roc"]["status"] == "match"
    # the R=-100 sibling must be rejected on ROC (hard violation)
    assert any("曲率" in r for r in body["rejection_reasons"])


def test_match_three_state_maybe_usable(client):
    _import_inventory(client)
    # ask for HR at 1064 with a flat mirror: the 1123-HR input mirror is
    # nominal-off-design; the stopband prior should say maybe_usable, and the
    # same surface being HT@1064 must veto it instead (conflict) — verify the
    # evaluator surfaces one of the two honest outcomes, never design_match.
    resp = client.post("/api/inventory/match", json={
        "role": "HR test",
        "category": "mirror",
        "surfaces": [{"wavelength_nm": 1064, "function": "HR"}],
        "roc_mm": "flat",
    })
    body = resp.json()
    statuses = {c["parameters"]["coatings"][0]["status"]
                for c in body["candidates"] + body["rejected_examples"]
                if c["name"] == "输入镜"}
    assert statuses and statuses <= {"maybe_usable", "conflict", "off"}
    assert "design_match" not in statuses


def test_match_unknown_coating_needs_measurement(client):
    _import_inventory(client)
    resp = client.post("/api/inventory/match", json={
        "role": "AR window test",
        "category": "mirror",
        "surfaces": [{"wavelength_nm": 1064, "function": "AR"}],
        "roc_mm": 200,
    })
    body = resp.json()
    mystery = next((c for c in body["candidates"] if c["name"] == "神秘镜"), None)
    assert mystery is not None
    assert mystery["must_measure"]                            # 不能确定是否镀膜 -> measure list
    assert mystery["parameters"]["coatings"][0]["status"] in ("unknown", "off")


# --- agent path -------------------------------------------------------------

def test_agent_task_matches_components(client):
    _import_inventory(client)
    case = client.post("/api/cases", json={
        "title": "Match test case", "cavity_type": "linear", "goal": "find mirrors",
        "parameters": {"component_requirement": {
            "category": "mirror",
            "surfaces": [{"wavelength_nm": 1064, "function": "HR"}],
            "roc_mm": 400,
        }},
    })
    task = client.post("/api/agent/tasks", json={
        "case_id": case.json()["id"], "goal": "从库存里选1064腔镜", "mode": "component_match",
    })
    assert task.status_code == 201, task.text
    body = task.json()
    assert body["status"] == "completed"
    compute = next(c for c in body["tool_calls"] if c["tool_name"] == "match_components")
    assert compute["output_json"]["eligible_count"] >= 1


def test_chat_routes_component_match(client):
    case = client.post("/api/cases", json={
        "title": "Route test", "cavity_type": "linear", "goal": "g",
    })
    resp = client.post("/api/agent/chat", json={
        "case_id": case.json()["id"],
        "message": "帮我从库存里选元件，找一块1064的HR镜",
    })
    assert resp.status_code == 200
    assert resp.json()["routed_mode"] == "component_match"
