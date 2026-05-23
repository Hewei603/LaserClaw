"""Tests for the tool router — 50+ routing test cases."""
from __future__ import annotations

import pytest

from app.agent.router import (
    TOOL_CHAT,
    TOOL_PLAN,
    TOOL_REPORT,
    TOOL_RESONATOR,
    TOOL_TROUBLESHOOTING,
    route_sync,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def assert_route(text: str, expected_tool: str) -> None:
    result = route_sync(text)
    assert result.selected_tool == expected_tool, (
        f"Query: {text!r}\n"
        f"Expected: {expected_tool}\n"
        f"Got: {result.selected_tool} (confidence={result.confidence:.2f}, reason={result.reason!r})"
    )


# ---------------------------------------------------------------------------
# generate_plan cases (Chinese)
# ---------------------------------------------------------------------------
class TestPlanRoutingChinese:
    def test_plan_01(self): assert_route("帮我制定一个实验计划", TOOL_PLAN)
    def test_plan_02(self): assert_route("请给出详细的实验步骤", TOOL_PLAN)
    def test_plan_03(self): assert_route("怎么搭建这个光路", TOOL_PLAN)
    def test_plan_04(self): assert_route("如何搭建 Nd:YAG 激光器", TOOL_PLAN)
    def test_plan_05(self): assert_route("给我一个实验方案", TOOL_PLAN)
    def test_plan_06(self): assert_route("实验流程是什么", TOOL_PLAN)
    def test_plan_07(self): assert_route("操作步骤有哪些", TOOL_PLAN)
    def test_plan_08(self): assert_route("怎么做这个实验", TOOL_PLAN)
    def test_plan_09(self): assert_route("搭建方案请给我", TOOL_PLAN)
    def test_plan_10(self): assert_route("如何进行倍频实验", TOOL_PLAN)


# ---------------------------------------------------------------------------
# generate_plan cases (English)
# ---------------------------------------------------------------------------
class TestPlanRoutingEnglish:
    def test_plan_en_01(self): assert_route("Give me an experiment plan", TOOL_PLAN)
    def test_plan_en_02(self): assert_route("What are the experimental steps?", TOOL_PLAN)
    def test_plan_en_03(self): assert_route("How to set up the optical path?", TOOL_PLAN)
    def test_plan_en_04(self): assert_route("Write a setup guide for this laser", TOOL_PLAN)
    def test_plan_en_05(self): assert_route("Describe the procedure for alignment", TOOL_PLAN)


# ---------------------------------------------------------------------------
# generate_troubleshooting cases (Chinese)
# ---------------------------------------------------------------------------
class TestTroubleshootingRoutingChinese:
    def test_ts_01(self): assert_route("激光不出光怎么办", TOOL_TROUBLESHOOTING)
    def test_ts_02(self): assert_route("功率低是什么原因", TOOL_TROUBLESHOOTING)
    def test_ts_03(self): assert_route("功率波动很大", TOOL_TROUBLESHOOTING)
    def test_ts_04(self): assert_route("光斑异常，有散射", TOOL_TROUBLESHOOTING)
    def test_ts_05(self): assert_route("激光不稳定怎么排查", TOOL_TROUBLESHOOTING)
    def test_ts_06(self): assert_route("出不了光，检查了电源", TOOL_TROUBLESHOOTING)
    def test_ts_07(self): assert_route("没有输出信号", TOOL_TROUBLESHOOTING)
    def test_ts_08(self): assert_route("输出不稳定，模式跳变", TOOL_TROUBLESHOOTING)
    def test_ts_09(self): assert_route("噪声很大，频率漂移", TOOL_TROUBLESHOOTING)
    def test_ts_10(self): assert_route("腔失调了，光斑变形", TOOL_TROUBLESHOOTING)
    def test_ts_11(self): assert_route("准直有问题，光路偏了", TOOL_TROUBLESHOOTING)
    def test_ts_12(self): assert_route("这个故障怎么处理", TOOL_TROUBLESHOOTING)


# ---------------------------------------------------------------------------
# generate_troubleshooting cases (English)
# ---------------------------------------------------------------------------
class TestTroubleshootingRoutingEnglish:
    def test_ts_en_01(self): assert_route("The laser is not lasing", TOOL_TROUBLESHOOTING)
    def test_ts_en_02(self): assert_route("Low output power, how to diagnose?", TOOL_TROUBLESHOOTING)
    def test_ts_en_03(self): assert_route("Power fluctuation is too high", TOOL_TROUBLESHOOTING)
    def test_ts_en_04(self): assert_route("Beam quality is poor, troubleshoot", TOOL_TROUBLESHOOTING)
    def test_ts_en_05(self): assert_route("Laser output is unstable", TOOL_TROUBLESHOOTING)


# ---------------------------------------------------------------------------
# generate_report cases (Chinese)
# ---------------------------------------------------------------------------
class TestReportRoutingChinese:
    def test_rpt_01(self): assert_route("帮我写一份实验报告", TOOL_REPORT)
    def test_rpt_02(self): assert_route("总结一下这次实验", TOOL_REPORT)
    def test_rpt_03(self): assert_route("整理实验记录", TOOL_REPORT)
    def test_rpt_04(self): assert_route("生成实验总结", TOOL_REPORT)
    def test_rpt_05(self): assert_route("数据总结请帮我写", TOOL_REPORT)
    def test_rpt_06(self): assert_route("实验结果整理一下", TOOL_REPORT)
    def test_rpt_07(self): assert_route("写报告，包含数据分析", TOOL_REPORT)


# ---------------------------------------------------------------------------
# generate_report cases (English)
# ---------------------------------------------------------------------------
class TestReportRoutingEnglish:
    def test_rpt_en_01(self): assert_route("Write an experiment report", TOOL_REPORT)
    def test_rpt_en_02(self): assert_route("Summarize the experiment results", TOOL_REPORT)
    def test_rpt_en_03(self): assert_route("Generate a data summary", TOOL_REPORT)
    def test_rpt_en_04(self): assert_route("Write up the experiment record", TOOL_REPORT)


# ---------------------------------------------------------------------------
# generate_resonator_draft cases (Chinese)
# ---------------------------------------------------------------------------
class TestResonatorRoutingChinese:
    def test_rez_01(self): assert_route("帮我生成 ReZonator 仿真输入", TOOL_RESONATOR)
    def test_rez_02(self): assert_route("腔稳定性分析", TOOL_RESONATOR)
    def test_rez_03(self): assert_route("腔长怎么设置", TOOL_RESONATOR)
    def test_rez_04(self): assert_route("曲率半径参数", TOOL_RESONATOR)
    def test_rez_05(self): assert_route("谐振腔设计方案", TOOL_RESONATOR)
    def test_rez_06(self): assert_route("腔型设计，线形腔", TOOL_RESONATOR)
    def test_rez_07(self): assert_route("腔模计算", TOOL_RESONATOR)
    def test_rez_08(self): assert_route("腔参数优化", TOOL_RESONATOR)


# ---------------------------------------------------------------------------
# generate_resonator_draft cases (English)
# ---------------------------------------------------------------------------
class TestResonatorRoutingEnglish:
    def test_rez_en_01(self): assert_route("Generate ReZonator simulation input", TOOL_RESONATOR)
    def test_rez_en_02(self): assert_route("Cavity stability analysis", TOOL_RESONATOR)
    def test_rez_en_03(self): assert_route("What cavity length should I use?", TOOL_RESONATOR)
    def test_rez_en_04(self): assert_route("Resonator design with radius of curvature", TOOL_RESONATOR)


# ---------------------------------------------------------------------------
# chat / qa fallback cases
# ---------------------------------------------------------------------------
class TestChatFallback:
    def test_chat_01(self): assert_route("激光的工作原理是什么", TOOL_CHAT)
    def test_chat_02(self): assert_route("Nd:YAG 晶体的特性", TOOL_CHAT)
    def test_chat_03(self): assert_route("What is stimulated emission?", TOOL_CHAT)
    def test_chat_04(self): assert_route("LBO 晶体的相位匹配条件", TOOL_CHAT)
    def test_chat_05(self): assert_route("Tell me about laser safety", TOOL_CHAT)
    def test_chat_06(self): assert_route("这个实验用什么泵浦源", TOOL_CHAT)
    def test_chat_07(self): assert_route("What wavelength does Nd:YAG emit?", TOOL_CHAT)


# ---------------------------------------------------------------------------
# Routing accuracy summary
# ---------------------------------------------------------------------------
def test_routing_accuracy_summary():
    """Compute and print routing accuracy across all test cases."""
    test_cases = [
        # (query, expected_tool)
        ("帮我制定一个实验计划", TOOL_PLAN),
        ("请给出详细的实验步骤", TOOL_PLAN),
        ("怎么搭建这个光路", TOOL_PLAN),
        ("如何搭建 Nd:YAG 激光器", TOOL_PLAN),
        ("给我一个实验方案", TOOL_PLAN),
        ("实验流程是什么", TOOL_PLAN),
        ("操作步骤有哪些", TOOL_PLAN),
        ("怎么做这个实验", TOOL_PLAN),
        ("搭建方案请给我", TOOL_PLAN),
        ("如何进行倍频实验", TOOL_PLAN),
        ("Give me an experiment plan", TOOL_PLAN),
        ("What are the experimental steps?", TOOL_PLAN),
        ("How to set up the optical path?", TOOL_PLAN),
        ("Write a setup guide for this laser", TOOL_PLAN),
        ("Describe the procedure for alignment", TOOL_PLAN),
        ("激光不出光怎么办", TOOL_TROUBLESHOOTING),
        ("功率低是什么原因", TOOL_TROUBLESHOOTING),
        ("功率波动很大", TOOL_TROUBLESHOOTING),
        ("光斑异常，有散射", TOOL_TROUBLESHOOTING),
        ("激光不稳定怎么排查", TOOL_TROUBLESHOOTING),
        ("出不了光，检查了电源", TOOL_TROUBLESHOOTING),
        ("没有输出信号", TOOL_TROUBLESHOOTING),
        ("输出不稳定，模式跳变", TOOL_TROUBLESHOOTING),
        ("噪声很大，频率漂移", TOOL_TROUBLESHOOTING),
        ("腔失调了，光斑变形", TOOL_TROUBLESHOOTING),
        ("准直有问题，光路偏了", TOOL_TROUBLESHOOTING),
        ("这个故障怎么处理", TOOL_TROUBLESHOOTING),
        ("The laser is not lasing", TOOL_TROUBLESHOOTING),
        ("Low output power, how to diagnose?", TOOL_TROUBLESHOOTING),
        ("Power fluctuation is too high", TOOL_TROUBLESHOOTING),
        ("Beam quality is poor, troubleshoot", TOOL_TROUBLESHOOTING),
        ("Laser output is unstable", TOOL_TROUBLESHOOTING),
        ("帮我写一份实验报告", TOOL_REPORT),
        ("总结一下这次实验", TOOL_REPORT),
        ("整理实验记录", TOOL_REPORT),
        ("生成实验总结", TOOL_REPORT),
        ("数据总结请帮我写", TOOL_REPORT),
        ("实验结果整理一下", TOOL_REPORT),
        ("写报告，包含数据分析", TOOL_REPORT),
        ("Write an experiment report", TOOL_REPORT),
        ("Summarize the experiment results", TOOL_REPORT),
        ("Generate a data summary", TOOL_REPORT),
        ("Write up the experiment record", TOOL_REPORT),
        ("帮我生成 ReZonator 仿真输入", TOOL_RESONATOR),
        ("腔稳定性分析", TOOL_RESONATOR),
        ("腔长怎么设置", TOOL_RESONATOR),
        ("曲率半径参数", TOOL_RESONATOR),
        ("谐振腔设计方案", TOOL_RESONATOR),
        ("腔型设计，线形腔", TOOL_RESONATOR),
        ("腔模计算", TOOL_RESONATOR),
        ("腔参数优化", TOOL_RESONATOR),
        ("Generate ReZonator simulation input", TOOL_RESONATOR),
        ("Cavity stability analysis", TOOL_RESONATOR),
        ("What cavity length should I use?", TOOL_RESONATOR),
        ("Resonator design with radius of curvature", TOOL_RESONATOR),
        ("激光的工作原理是什么", TOOL_CHAT),
        ("Nd:YAG 晶体的特性", TOOL_CHAT),
        ("What is stimulated emission?", TOOL_CHAT),
        ("LBO 晶体的相位匹配条件", TOOL_CHAT),
        ("Tell me about laser safety", TOOL_CHAT),
        ("这个实验用什么泵浦源", TOOL_CHAT),
        ("What wavelength does Nd:YAG emit?", TOOL_CHAT),
    ]

    correct = 0
    wrong = []
    for query, expected in test_cases:
        result = route_sync(query)
        if result.selected_tool == expected:
            correct += 1
        else:
            wrong.append((query, expected, result.selected_tool))

    accuracy = correct / len(test_cases)
    print(f"\nRouting accuracy: {correct}/{len(test_cases)} = {accuracy:.1%}")
    if wrong:
        print("Wrong predictions:")
        for q, exp, got in wrong:
            print(f"  Query: {q!r} | Expected: {exp} | Got: {got}")

    assert accuracy >= 0.90, f"Routing accuracy {accuracy:.1%} is below 90% threshold"
