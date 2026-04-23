"""
模拟AI提供者测试
"""
import pytest
from app.providers.mock import MockProvider


@pytest.mark.asyncio
async def test_mock_provider_generate_plan():
    """测试模拟提供者生成计划"""
    provider = MockProvider()
    case_data = {
        "cavity_type": "linear",
        "goal": "测试目标"
    }

    result = await provider.generate_plan(case_data)
    assert "disclaimer" in result
    assert "steps" in result
    assert len(result["steps"]) > 0


@pytest.mark.asyncio
async def test_mock_provider_generate_rezonator():
    """测试模拟提供者生成ReZonator模式"""
    provider = MockProvider()
    case_data = {
        "cavity_type": "ring",
        "parameters": {"波长": "800nm"}
    }

    result = await provider.generate_rezonator_schema(case_data)
    assert "disclaimer" in result
    assert "cavity_type" in result
    assert "elements" in result


@pytest.mark.asyncio
async def test_mock_provider_generate_troubleshooting():
    """测试模拟提供者生成故障排查"""
    provider = MockProvider()
    symptoms = ["无输出", "热效应"]
    case_data = {"cavity_type": "linear"}

    result = await provider.generate_troubleshooting(symptoms, case_data)
    assert "disclaimer" in result
    assert "suggestions" in result
    assert len(result["suggestions"]) == 2


@pytest.mark.asyncio
async def test_mock_provider_generate_report():
    """测试模拟提供者生成报告"""
    provider = MockProvider()
    case_data = {
        "title": "测试案例",
        "cavity_type": "linear",
        "goal": "测试目标"
    }

    result = await provider.generate_report(case_data)
    assert "disclaimer" in result
    assert "title" in result
    assert "sections" in result
