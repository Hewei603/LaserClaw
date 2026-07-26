"""
内容生成API测试
"""
import pytest


@pytest.mark.asyncio
async def test_generate_plan(client):
    """测试生成实验计划"""
    # 创建案例
    create_response = client.post("/api/cases", json={
        "title": "测试案例",
        "cavity_type": "linear",
        "goal": "测试实验计划生成"
    })
    case_id = create_response.json()["id"]

    # 生成计划
    response = client.post(f"/api/cases/{case_id}/generate-plan")
    assert response.status_code == 200
    data = response.json()
    assert data["content_type"] == "plan"
    assert "content" in data
    assert "disclaimer" in data["content"]



@pytest.mark.asyncio
async def test_generate_troubleshooting(client):
    """测试生成故障排查"""
    # 创建案例
    create_response = client.post("/api/cases", json={
        "title": "测试案例",
        "cavity_type": "linear",
        "goal": "测试故障排查",
        "symptoms": ["无输出", "热效应"]
    })
    case_id = create_response.json()["id"]

    # 生成故障排查
    response = client.post(f"/api/cases/{case_id}/generate-troubleshooting")
    assert response.status_code == 200
    data = response.json()
    assert data["content_type"] == "troubleshooting"
    assert "content" in data
    assert "suggestions" in data["content"]


@pytest.mark.asyncio
async def test_generate_report(client):
    """测试生成实验报告"""
    # 创建案例
    create_response = client.post("/api/cases", json={
        "title": "测试案例",
        "cavity_type": "linear",
        "goal": "测试报告生成"
    })
    case_id = create_response.json()["id"]

    # 生成报告
    response = client.post(f"/api/cases/{case_id}/generate-report")
    assert response.status_code == 200
    data = response.json()
    assert data["content_type"] == "report"
    assert "content" in data
    assert "title" in data["content"]


@pytest.mark.asyncio
async def test_list_generated_contents(client):
    """测试获取生成内容列表"""
    # 创建案例
    create_response = client.post("/api/cases", json={
        "title": "测试案例",
        "cavity_type": "linear",
        "goal": "测试内容列表"
    })
    case_id = create_response.json()["id"]

    # 生成多个内容
    client.post(f"/api/cases/{case_id}/generate-plan")
    client.post(f"/api/cases/{case_id}/generate-report")

    # 获取所有生成内容
    response = client.get(f"/api/cases/{case_id}/generated-contents")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # 按类型过滤
    response = client.get(f"/api/cases/{case_id}/generated-contents?content_type=plan")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["content_type"] == "plan"
