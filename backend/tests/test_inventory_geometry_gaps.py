"""Geometry parsing regressions pinned against the lab's REAL workbook writings.

Every input string below appears verbatim in 127镜片统计 (the lab's actual
inventory sheet). Before this fix, 96 rows had geometry text that produced no
structured field — the evaluator then told the student to go measure a number
the workbook already stated.
"""
import io

import openpyxl
import pytest

from app.inventory.parser import parse_geometry

pytestmark = pytest.mark.usefixtures("db")


# --- parser-level: real-world cell writings ---------------------------------

def test_lens_focal_length_variants():
    # F=300mm / f=250 mm / bare F100 — all real rows from the lens sheet.
    assert parse_geometry("D=25mm", "F=300mm").focal_length_mm == 300.0
    assert parse_geometry("D=25.4mm", "f=250 mm").focal_length_mm == 250.0
    assert parse_geometry("Φ25*5mm", "F100").focal_length_mm == 100.0
    assert parse_geometry("D=25.7mm", "凸透镜，f=250 mm").focal_length_mm == 250.0


def test_plano_concave_lens_keeps_sign_and_roc():
    geo = parse_geometry("D=25.4mm", "F=-99.6，R=-51.5")
    assert geo.focal_length_mm == -99.6      # diverging lens
    assert geo.roc_mm == 51.5                # ROC magnitude, as for mirrors


def test_diameter_times_thickness_shorthand():
    geo = parse_geometry("Φ25*5mm", "R=-300mm")
    assert geo.diameter_mm == 25.0
    assert geo.thickness_mm == 5.0
    assert geo.roc_mm == 300.0

    geo = parse_geometry("D=25.4*5mm", "R=-400")
    assert geo.diameter_mm == 25.4
    assert geo.thickness_mm == 5.0
    assert geo.roc_mm == 400.0


def test_diameter_lower_bound_form():
    assert parse_geometry("D>18mm").diameter_mm == 18.0


def test_focal_regex_does_not_eat_letters():
    # "HF" 或数字后缀里的 F 不能当焦距
    assert parse_geometry("HF膜 D=25mm").focal_length_mm is None


def test_plain_forms_still_parse():
    geo = parse_geometry("D=25mm", "R=-100")
    assert geo.diameter_mm == 25.0
    assert geo.roc_mm == 100.0
    assert parse_geometry("", "平镜").roc_is_flat is True
    geo = parse_geometry("3*3*5mm3，θ=159.6°")
    assert geo.dimensions == "3*3*5mm3"
    assert geo.cut_angle_theta_deg == 159.6


# --- importer-level: unparsed geometry must be visible ----------------------

def _workbook_bytes(rows_sheet1):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["序号", "物料名称", "镀膜S1", "镀膜S2", "规格", "曲率", "数量", "存放地", "负责人", "备注"])
    for row in rows_sheet1:
        ws.append(row)
    wb.create_sheet("Sheet2")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _import(client, content):
    resp = client.post(
        "/api/inventory/import",
        files={"file": ("geo.xlsx", content,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers={"x-user-id": "1", "x-user-role": "admin"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_unparsed_geometry_cell_goes_to_review_queue(client):
    report = _import(client, _workbook_bytes([
        [1, "棱镜", "S1:未镀膜", "", "顶角60.6°", "", 1, "127", "某人", ""],
    ]))
    assert report["imported"] == 1
    # The apex-angle prism parses no geometry field: it must surface, not vanish.
    assert report["partial"] + report["needs_review"] >= 1
    queue_notes = " ".join(str(e) for e in report.get("review_queue", []))
    assert "几何列未解析" in queue_notes


def test_parsed_lens_row_is_not_flagged(client):
    report = _import(client, _workbook_bytes([
        [1, "平凸透镜", "S1:未镀膜", "", "D=25.4mm", "f=100 mm", 1, "127", "某人", ""],
    ]))
    assert report["imported"] == 1
    queue_notes = " ".join(str(e) for e in report.get("review_queue", []))
    assert "几何列未解析" not in queue_notes
    items = client.get("/api/inventory/items?category=lens").json()
    assert items and items[0]["focal_length_mm"] == 100.0
    assert items[0]["diameter_mm"] == 25.4
