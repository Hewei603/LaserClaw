"""Power transfer curve module: fitting, cross-series loss analysis, agent path."""
import io

import numpy as np

from app.physics.laser_metrics import caird, findlay_clay, fit_power_curve


# --- pure fitting ------------------------------------------------------------

def _synthetic_curve(threshold, slope, pmax=6.0, n=13, noise=0.0, seed=1):
    rng = np.random.default_rng(seed)
    pump = np.linspace(0.0, pmax, n)
    out = np.where(pump > threshold, slope * (pump - threshold), 0.0)
    out = np.clip(out + rng.normal(0, noise, n), 0, None)
    return list(pump), list(out)


def test_fit_recovers_threshold_and_slope():
    pump, out = _synthetic_curve(2.0, 0.40, noise=0.002)
    fit = fit_power_curve(pump, out)
    assert fit["status"] == "completed"
    assert abs(fit["threshold_pump"] - 2.0) < 0.05
    assert abs(fit["slope_efficiency"] - 0.40) < 0.01
    assert fit["r_squared"] > 0.999


def test_fit_rejects_flat_data():
    fit = fit_power_curve([1, 2, 3, 4], [0.0, 0.0, 0.0, 0.0])
    assert fit["status"] == "failed"


def test_fit_warns_on_poor_linearity():
    pump, out = _synthetic_curve(2.0, 0.40, noise=0.15, seed=3)
    fit = fit_power_curve(pump, out)
    if fit["status"] == "completed":
        assert fit["warnings"]  # noisy data must carry a warning, not silent confidence


def test_findlay_clay_and_caird_recover_loss():
    # ground truth: round-trip loss 2%, intrinsic slope 60%
    series = [{"output_coupler_T_pct": T,
               "threshold_pump": 50 * (T / 100 + 0.02),
               "slope_efficiency": 0.6 / (1 + 0.02 / (T / 100))}
              for T in (2, 5, 10)]
    fc = findlay_clay(series)
    cd = caird(series)
    assert fc["applicable"] and abs(fc["round_trip_loss_pct"] - 2.0) < 0.05
    assert cd["applicable"] and abs(cd["round_trip_loss_pct"] - 2.0) < 0.05
    assert abs(cd["intrinsic_slope_pct"] - 60.0) < 0.5


def test_loss_analyses_need_two_couplings():
    series = [{"output_coupler_T_pct": 5, "threshold_pump": 3.5, "slope_efficiency": 0.4}]
    assert findlay_clay(series) is None
    assert caird(series) is None


# --- module through the API --------------------------------------------------

def _create_case(client):
    r = client.post("/api/cases", json={
        "title": "Power curve case", "cavity_type": "linear", "goal": "characterize",
    })
    assert r.status_code == 201
    return r.json()["id"]


def _run_series(client, case_id, label, T_pct, threshold, slope, pmax=14.0):
    module = client.post(f"/api/cases/{case_id}/modules", json={
        "module_type": "power_curve", "title": label,
        "config_json": {"output_coupler_T_pct": T_pct, "label": label,
                        "pump_unit": "W", "output_unit": "W"},
    }).json()
    pump, out = _synthetic_curve(threshold, slope, pmax=pmax, n=17)
    csv_bytes = "\n".join(f"{p},{o}" for p, o in zip(pump, out)).encode()
    up = client.post(f"/api/cases/modules/{module['id']}/files",
                     files={"file": (f"{label}.csv", io.BytesIO(csv_bytes), "text/csv")})
    assert up.status_code in (200, 201), up.text
    run = client.post(f"/api/cases/modules/{module['id']}/run", json={"config_json": {}})
    assert run.status_code == 200, run.text
    return run.json()["result_json"]


def test_power_curve_module_fits_uploaded_csv(client):
    case_id = _create_case(client)
    result = _run_series(client, case_id, "T=5%", 5, threshold=2.0, slope=0.40)
    assert result["status"] == "completed"
    assert abs(result["fit"]["threshold_pump"] - 2.0) < 0.05
    assert "阈值" in result["summary"]


def test_power_curve_needs_input_without_data(client):
    case_id = _create_case(client)
    module = client.post(f"/api/cases/{case_id}/modules",
                         json={"module_type": "power_curve"}).json()
    run = client.post(f"/api/cases/modules/{module['id']}/run", json={"config_json": {}})
    assert run.json()["result_json"]["status"] == "needs_input"


def test_cross_series_findlay_clay(client):
    # three series with different output couplers -> automatic loss analysis
    case_id = _create_case(client)
    loss = 0.02
    for T in (2, 5, 10):
        thr = 50 * (T / 100 + loss)
        slope = 0.6 / (1 + loss / (T / 100))
        result = _run_series(client, case_id, f"T={T}%", T, thr, slope)
    assert len(result["comparison"]) == 3
    assert result["findlay_clay"]["applicable"]
    assert abs(result["findlay_clay"]["round_trip_loss_pct"] - 2.0) < 0.3
    assert result["caird"]["applicable"]
    assert "Findlay-Clay" in result["summary"]


def test_inline_data_and_agent_routing(client):
    case_id = _create_case(client)
    module = client.post(f"/api/cases/{case_id}/modules", json={
        "module_type": "power_curve",
        "config_json": {"data": {"pump": [0, 1, 2, 3, 4, 5],
                                 "output": [0, 0, 0.02, 0.42, 0.81, 1.20]}},
    }).json()
    run = client.post(f"/api/cases/modules/{module['id']}/run", json={"config_json": {}})
    assert run.json()["result_json"]["status"] == "completed"

    chat = client.post("/api/agent/chat", json={
        "case_id": case_id, "message": "帮我分析一下功率曲线，算阈值和斜率效率",
    })
    assert chat.status_code == 200
    assert chat.json()["routed_mode"] == "power_curve"
