"""Crystal cut-angle matching in the L1 evaluator.

Anchors (computed by the physics kernel, cross-checked against vendor labels in
the lab's real workbook):

* LBO SHG-I @1064 -> xy plane, theta=90, phi=11.36
* LBO SHG-I @1123 -> xy plane, theta=90, phi=7.55   (delta-phi to 1064 cut: 3.8)
* LBO SHG-I @740  -> xy plane, theta=90, phi=38.23  (delta-phi to 1064 cut: 26.9)
* BIBO SHG-I @914 -> yz plane, theta=20.33 (vendors label the equivalent 159.6)

The lab's BIBO is labelled theta=159.6 and its coating says 914/517 — the
first-principles check that this evaluator reproduces that label to 0.1 degree
is what makes the three-state verdicts trustworthy.
"""
from app.inventory.evaluator import evaluate_candidates
from app.models import InventoryItem


def _crystal(name, theta=None, phi=None, category="nonlinear_crystal", qty=1, material=None):
    return InventoryItem(
        category=category, name=name, quantity=qty,
        cut_angle_theta_deg=theta, cut_angle_phi_deg=phi, material=material,
    )


def _seed(db, *items):
    for item in items:
        db.add(item)
    db.commit()


def _match(db, **pm):
    return evaluate_candidates(db, {"role": "shg", "phase_match": pm})


def test_exact_cut_is_design_match(db):
    _seed(db, _crystal("LBO倍频晶体", theta=90.0, phi=11.4))
    out = _match(db, lambda1_nm=1064, pm_type="I")
    assert out["eligible_count"] == 1
    cut = out["candidates"][0]["parameters"]["cut_angle"]
    assert cut["status"] == "design_match"
    assert cut["deviation_deg"] <= 0.1
    assert cut["required"]["plane"] == "xy"


def test_nearby_cut_is_retunable_and_goes_to_measure_list(db):
    # The lab's real situation: an LBO cut for the 1123 line asked to do 1064.
    _seed(db, _crystal("LBO倍频晶体", theta=90.0, phi=7.55))
    out = _match(db, lambda1_nm=1064, pm_type="I")
    assert out["eligible_count"] == 1
    v = out["candidates"][0]
    cut = v["parameters"]["cut_angle"]
    assert cut["status"] == "maybe_usable"
    assert 3.0 < cut["deviation_deg"] < 5.0
    assert any("切角重调" in m for m in v["must_measure"])


def test_far_cut_is_a_hard_violation(db):
    _seed(db, _crystal("LBO倍频晶体", theta=90.0, phi=38.23))
    out = _match(db, lambda1_nm=1064, pm_type="I")
    assert out["eligible_count"] == 0
    assert any("切角" in r for r in out["rejection_reasons"])


def test_bibo_judged_as_bibo_not_lbo(db):
    # theta=159.6 is the vendor's label for the computed 20.33-degree 914 cut
    # (180-theta equivalence). Judged for 914 it must be a design match; judged
    # for 1064 the same crystal is >5 degrees off and must be vetoed.
    _seed(db, _crystal("BIBO晶体", theta=159.6))
    ok = _match(db, lambda1_nm=914, pm_type="I")
    assert ok["eligible_count"] == 1
    cut = ok["candidates"][0]["parameters"]["cut_angle"]
    assert cut["status"] == "design_match"
    assert cut["deviation_deg"] <= 0.1
    # phi is unlabelled on the item, so even a match keeps a measurement flag
    assert cut["needs_measurement"] is True

    bad = _match(db, lambda1_nm=1064, pm_type="I")
    assert bad["eligible_count"] == 0


def test_unlabelled_cut_is_must_measure_not_veto(db):
    _seed(db, _crystal("LBO倍频晶体"))
    out = _match(db, lambda1_nm=1064, pm_type="I")
    assert out["eligible_count"] == 1
    v = out["candidates"][0]
    assert v["parameters"]["cut_angle"]["status"] == "unknown"
    assert any("切角" in m for m in v["must_measure"])


def test_material_restriction_vetoes_other_materials(db):
    _seed(db, _crystal("BIBO晶体", theta=159.6))
    out = _match(db, lambda1_nm=1064, pm_type="I", crystal="lbo")
    assert out["eligible_count"] == 0
    assert any("材料" in r for r in out["rejection_reasons"])


def test_mirrors_and_gain_crystals_are_excluded(db):
    _seed(db,
          _crystal("LBO倍频晶体", theta=90.0, phi=11.4),
          _crystal("Yb:CALGO激光晶体", category="gain_crystal"),
          InventoryItem(category="mirror", name="1064腔镜", quantity=3, roc_is_flat=True))
    out = _match(db, lambda1_nm=1064, pm_type="I")
    # Neither the mirror nor the gain crystal may even be evaluated: a
    # cut-angle requirement is a frequency-conversion-crystal requirement, and
    # 20 Yb/Nd hosts flagged "material unknown" would bury the two LBO rows
    # that matter (observed against the lab's real 247-item workbook).
    assert out["total_evaluated"] == 1


def test_isotropic_crystal_is_vetoed_not_unknown(db):
    # 克尔介质 CaF2 lives in crystal_other, but an isotropic material can never
    # angle-phase-match — that is physics, not a missing label, so it must be
    # a hard veto rather than a "go measure it" item.
    _seed(db, _crystal("克尔介质CaF2晶体", category="crystal_other"))
    out = _match(db, lambda1_nm=1064, pm_type="I")
    assert out["eligible_count"] == 0
    assert any("不是角度相位匹配晶体" in r or "CAF2" in r.upper() for r in out["rejection_reasons"])


def test_retunable_does_not_dominate_exact_cut(db):
    _seed(db,
          _crystal("LBO倍频晶体A", theta=90.0, phi=11.4),
          _crystal("LBO倍频晶体B", theta=90.0, phi=7.55))
    out = _match(db, lambda1_nm=1064, pm_type="I")
    assert out["eligible_count"] == 2
    top = out["candidates"][0]
    assert top["name"] == "LBO倍频晶体A"
    assert top["frontier"] is True
    other = out["candidates"][1]
    assert other["frontier"] is False  # dominated: worse cut status and deviation


def test_assumed_material_never_reaches_design_match(db):
    # A crystal whose material cannot be identified, matched under an explicit
    # crystal=lbo restriction, gets judged against ASSUMED-material physics.
    # Even a perfect angular agreement must stay "maybe_usable + confirm the
    # material" — a label-less crystal never "matches by design".
    _seed(db, _crystal("倍频晶体(未知材料)", theta=90.0, phi=11.4))
    out = _match(db, lambda1_nm=1064, pm_type="I", crystal="lbo")
    assert out["eligible_count"] == 1
    v = out["candidates"][0]
    cut = v["parameters"]["cut_angle"]
    assert cut["status"] == "maybe_usable"
    assert cut.get("material_assumed") is True
    assert "确认材料" in cut["detail"]
    assert any("确认材料" in m or "假定" in m for m in v["must_measure"])


def test_assumed_material_mismatch_is_not_a_veto(db):
    # Same unidentified crystal with an angle far from the LBO solution: the
    # physics was computed for an ASSUMED material, so this is "unknown, go
    # confirm", never a confident hard rejection.
    _seed(db, _crystal("倍频晶体(未知材料)", theta=90.0, phi=38.2))
    out = _match(db, lambda1_nm=1064, pm_type="I", crystal="lbo")
    assert out["eligible_count"] == 1
    assert out["candidates"][0]["parameters"]["cut_angle"]["status"] == "unknown"


def test_missing_lambda1_degrades_instead_of_500(db):
    # The case-module path merges raw case parameters into the requirement
    # without pydantic; a phase_match dict missing lambda1_nm must not KeyError.
    _seed(db, _crystal("LBO倍频晶体", theta=90.0, phi=11.4))
    out = evaluate_candidates(db, {"role": "shg", "phase_match": {"pm_type": "I"}})
    assert out["eligible_count"] == 1
    cut = out["candidates"][0]["parameters"]["cut_angle"]
    assert cut["status"] == "unknown"
    assert "lambda1_nm" in cut["detail"]


def test_match_api_round_trip(client):
    # Through the REST schema: nested phase_match survives validation.
    resp = client.post("/api/inventory/match", json={
        "role": "SHG crystal",
        "phase_match": {"lambda1_nm": 1064, "pm_type": "I"},
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["requirement"]["phase_match"]["lambda1_nm"] == 1064
