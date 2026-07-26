"""RAG retrieval evaluation dataset — 30+ queries with expected sources/keywords.

Run with: pytest backend/tests/eval_rag_dataset.py -v -s
"""
from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# RAG evaluation dataset
# Each entry: (query, expected_keywords, expected_source_hint)
# ---------------------------------------------------------------------------
RAG_EVAL_DATASET = [
    # --- Laser safety SOP ---
    ("激光防护眼镜的光密度要求", ["OD", "光密度", "防护眼镜"], "laser_safety_sop"),
    ("Class 4 激光的危害", ["Class 4", "漫反射", "危险"], "laser_safety_sop"),
    ("激光实验室紧急程序", ["紧急", "关闭激光", "就医"], "laser_safety_sop"),
    ("激光安全操作前检查清单", ["检查清单", "光束挡板", "防护眼镜"], "laser_safety_sop"),
    ("眼部受伤后怎么处理", ["眼部", "就医", "激光波长"], "laser_safety_sop"),
    ("激光实验室进入控制要求", ["警告标志", "非授权", "防护眼镜"], "laser_safety_sop"),
    ("What PPE is required for laser operation?", ["goggles", "OD", "protective"], "laser_safety_sop"),
    ("Laser fire emergency procedure", ["CO2", "extinguisher", "evacuate"], "laser_safety_sop"),

    # --- Optical alignment SOP ---
    ("光路准直的两光阑法", ["两光阑", "光阑", "准直"], "optical_alignment_sop"),
    ("线形腔准直步骤", ["HR 镜", "OC 镜", "增益介质"], "optical_alignment_sop"),
    ("准直质量评估标准", ["重复性", "透过率", "稳定性"], "optical_alignment_sop"),
    ("光斑不圆怎么处理", ["晶体", "倾斜", "角度"], "optical_alignment_sop"),
    ("How to align an optical cavity?", ["iris", "diaphragm", "alignment"], "optical_alignment_sop"),
    ("Beam alignment quality criteria", ["repeatability", "transmission", "stability"], "optical_alignment_sop"),

    # --- Power meter manual ---
    ("功率计使用前需要预热多久", ["预热", "5 分钟", "稳定"], "power_meter_manual"),
    ("热电堆探头适用波长范围", ["热电堆", "190nm", "20μm"], "power_meter_manual"),
    ("功率计读数不稳定怎么排查", ["不稳定", "激光不稳定", "振动"], "power_meter_manual"),
    ("功率计过载报警怎么处理", ["过载", "量程", "探头"], "power_meter_manual"),
    ("How to use a laser power meter?", ["warm up", "aperture", "range"], "power_meter_manual"),
    ("Power meter calibration requirements", ["calibration", "annual", "certificate"], "power_meter_manual"),

    # --- Nd:YAG / LBO intro ---
    ("Nd:YAG 晶体的荧光寿命", ["荧光寿命", "230 μs", "Nd:YAG"], "ndyag_lbo_intro"),
    ("LBO 晶体的损伤阈值", ["损伤阈值", "25 GW", "LBO"], "ndyag_lbo_intro"),
    ("1064nm 倍频到 532nm 的相位匹配", ["相位匹配", "532", "LBO"], "ndyag_lbo_intro"),
    ("Nd:YAG 热透镜效应", ["热透镜", "折射率", "光束质量"], "ndyag_lbo_intro"),
    ("LBO 和 KTP 的对比", ["LBO", "KTP", "损伤阈值"], "ndyag_lbo_intro"),
    ("What is the emission wavelength of Nd:YAG?", ["1064", "nm", "wavelength"], "ndyag_lbo_intro"),
    ("LBO phase matching temperature for SHG", ["148", "temperature", "NCPM"], "ndyag_lbo_intro"),

    # --- ReZonator simulation ---
    ("ReZonator 仿真输入文件格式", ["rz", "Element", "mirror"], "rezonator_simulation_example"),
    ("腔稳定性参数 g1g2 的范围", ["g₁g₂", "稳定", "0–1"], "rezonator_simulation_example"),
    ("Nd:YAG 线形腔的腔长范围", ["100", "175", "稳定"], "rezonator_simulation_example"),
    ("热透镜对腔稳定性的影响", ["热透镜", "焦距", "补偿"], "rezonator_simulation_example"),
    ("How to set up ReZonator for linear cavity?", ["linear", "cavity", "element"], "rezonator_simulation_example"),

    # --- Fault troubleshooting records ---
    ("Nd:YAG 激光器无输出的排查步骤", ["泵浦光", "腔镜", "污染"], "fault_troubleshooting_records"),
    ("OC 镜污染导致激光无输出", ["OC 镜", "污染", "指纹"], "fault_troubleshooting_records"),
    ("532nm 功率波动的原因", ["LBO", "温控", "PID"], "fault_troubleshooting_records"),
    ("光斑质量下降 M2 升高", ["M²", "HR 镜", "准直"], "fault_troubleshooting_records"),
    ("激光器故障排查记录", ["故障", "排查", "根本原因"], "fault_troubleshooting_records"),
]


def evaluate_rag_hit(query: str, results: list[dict], expected_keywords: list[str], top_k: int = 3) -> dict:
    """Check if top-k results contain expected keywords."""
    top_results = results[:top_k]
    all_text = " ".join(r.get("text", "") + " " + r.get("source_title", "") for r in top_results).lower()

    hits = [kw for kw in expected_keywords if kw.lower() in all_text]
    hit_rate = len(hits) / len(expected_keywords) if expected_keywords else 0.0

    return {
        "query": query,
        "top_k": top_k,
        "expected_keywords": expected_keywords,
        "matched_keywords": hits,
        "keyword_hit_rate": hit_rate,
        "top3_hit": hit_rate > 0,
    }


# ---------------------------------------------------------------------------
# pytest integration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query,keywords,source_hint", RAG_EVAL_DATASET[:5])
def test_rag_dataset_structure(query, keywords, source_hint):
    """Verify dataset entries are well-formed."""
    assert isinstance(query, str) and len(query) > 5
    assert isinstance(keywords, list) and len(keywords) >= 1
    assert isinstance(source_hint, str) and len(source_hint) > 0


def test_rag_dataset_size():
    """Ensure we have at least 30 evaluation queries."""
    assert len(RAG_EVAL_DATASET) >= 30, f"Only {len(RAG_EVAL_DATASET)} queries, need >= 30"


def test_rag_dataset_covers_all_sources():
    """Ensure all 5 knowledge sources are covered."""
    sources = {entry[2] for entry in RAG_EVAL_DATASET}
    expected_sources = {
        "laser_safety_sop",
        "optical_alignment_sop",
        "power_meter_manual",
        "ndyag_lbo_intro",
        "rezonator_simulation_example",
        "fault_troubleshooting_records",
    }
    missing = expected_sources - sources
    assert not missing, f"Missing coverage for sources: {missing}"


def test_evaluate_rag_hit_function():
    """Test the hit evaluation helper."""
    results = [
        {"text": "激光防护眼镜 OD 光密度要求", "source_title": "laser_safety_sop"},
        {"text": "Class 4 激光危害", "source_title": "laser_safety_sop"},
        {"text": "其他内容", "source_title": "other"},
    ]
    result = evaluate_rag_hit("防护眼镜", results, ["OD", "光密度", "防护眼镜"])
    assert result["top3_hit"]
    assert result["keyword_hit_rate"] > 0
