"""
实验案例API测试
"""


def test_create_case(client):
    """测试创建案例"""
    case_data = {
        "title": "测试案例",
        "description": "这是一个测试案例",
        "cavity_type": "linear",
        "goal": "测试目标",
        "parameters": {"波长": "1064nm"},
        "symptoms": ["无输出"]
    }

    response = client.post("/api/cases", json=case_data)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == case_data["title"]
    assert data["cavity_type"] == case_data["cavity_type"]
    assert "id" in data


def test_list_cases(client):
    """测试获取案例列表"""
    # 创建几个案例
    for i in range(3):
        client.post("/api/cases", json={
            "title": f"案例 {i}",
            "cavity_type": "linear",
            "goal": f"目标 {i}"
        })

    response = client.get("/api/cases")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3


def test_get_case(client):
    """测试获取单个案例"""
    # 创建案例
    create_response = client.post("/api/cases", json={
        "title": "测试案例",
        "cavity_type": "ring",
        "goal": "测试目标"
    })
    case_id = create_response.json()["id"]

    # 获取案例
    response = client.get(f"/api/cases/{case_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == case_id
    assert data["title"] == "测试案例"


def test_get_nonexistent_case(client):
    """测试获取不存在的案例"""
    response = client.get("/api/cases/999")
    assert response.status_code == 404


def test_update_case(client):
    """测试更新案例"""
    # 创建案例
    create_response = client.post("/api/cases", json={
        "title": "原标题",
        "cavity_type": "linear",
        "goal": "原目标"
    })
    case_id = create_response.json()["id"]

    # 更新案例
    update_data = {
        "title": "新标题",
        "goal": "新目标"
    }
    response = client.put(f"/api/cases/{case_id}", json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "新标题"
    assert data["goal"] == "新目标"


def test_delete_case(client):
    """测试删除案例"""
    # 创建案例
    create_response = client.post("/api/cases", json={
        "title": "待删除案例",
        "cavity_type": "linear",
        "goal": "测试目标"
    })
    case_id = create_response.json()["id"]

    # 删除案例
    response = client.delete(f"/api/cases/{case_id}")
    assert response.status_code == 204

    # 验证已删除
    get_response = client.get(f"/api/cases/{case_id}")
    assert get_response.status_code == 404


def test_invalid_cavity_type(client):
    """测试无效的腔型"""
    response = client.post("/api/cases", json={
        "title": "测试",
        "cavity_type": "invalid",
        "goal": "测试"
    })
    assert response.status_code == 422
