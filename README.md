# LaserClaw

**LaserClaw** 是一个垂直AI代理应用，用于激光实验辅助。它是一个AI辅助工作流系统，提供实验计划、ReZonator模式/模板草稿、基于症状的故障排查、实验案例记录和报告生成等功能。

> ⚠️ **重要提示**: LaserClaw 是实验工作流辅助系统，不是直接硬件控制系统。所有AI生成的内容都是启发式建议，需要人工验证。

## 功能特性

- 🔬 **实验案例管理**: 创建、查看、编辑和删除激光实验案例
- 📋 **实验计划生成**: 基于实验目标和腔型自动生成结构化的实验步骤
- 🎯 **ReZonator模式草稿**: 根据腔型和参数生成ReZonator模式/模板草稿
- 🔧 **故障排查**: 基于观察到的症状提供可能的原因分析和解决方案
- 📊 **报告生成**: 自动生成结构化的实验报告
- 📎 **附件管理**: 上传和查看实验相关的图片、笔记、数据文件和ReZonator模式文件
- 🎭 **演示模式**: 内置模拟AI提供者，无需外部API密钥即可演示所有功能

## 技术栈

### 后端
- **FastAPI**: 现代、快速的Python Web框架
- **SQLAlchemy**: Python SQL工具包和ORM
- **PostgreSQL**: 强大的开源关系型数据库
- **Pydantic**: 数据验证和设置管理

### 前端
- **React 18**: 用户界面库
- **Vite**: 下一代前端构建工具
- **React Router**: 声明式路由
- **Axios**: HTTP客户端

### 部署
- **Docker Compose**: 容器编排
- **本地文件存储**: 附件存储

## 架构

```
LaserClaw/
├── backend/              # FastAPI后端
│   ├── app/
│   │   ├── main.py      # 应用入口
│   │   ├── config.py    # 配置管理
│   │   ├── database.py  # 数据库连接
│   │   ├── models/      # SQLAlchemy模型
│   │   ├── schemas/     # Pydantic模式
│   │   ├── api/         # API路由
│   │   ├── services/    # 业务逻辑（未来扩展）
│   │   └── providers/   # AI提供者抽象
│   ├── tests/           # pytest测试
│   ├── seed_data.py     # 数据库种子数据
│   └── requirements.txt
├── frontend/            # React前端
│   ├── src/
│   │   ├── pages/       # 页面组件
│   │   ├── components/  # 可复用组件（未来扩展）
│   │   └── api/         # API客户端
│   └── package.json
├── docker-compose.yml   # Docker编排配置
├── docs/                # 文档
└── README.md
```

## 快速开始

### 前置要求

- Docker 和 Docker Compose
- Git

### 安装步骤

1. **克隆仓库**

```bash
git clone <repository-url>
cd LaserClaw
```

2. **启动服务**

```bash
docker-compose up -d
```

这将启动三个服务:
- PostgreSQL 数据库 (端口 5432)
- FastAPI 后端 (端口 8000)
- React 前端 (端口 5173)

3. **填充演示数据**

```bash
docker-compose exec backend python seed_data.py
```

4. **访问应用**

打开浏览器访问: http://localhost:5173

API文档: http://localhost:8000/docs

### 停止服务

```bash
docker-compose down
```

### 查看日志

```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f backend
docker-compose logs -f frontend
```

## 演示流程

### 1. 查看演示案例

启动应用后，点击"实验案例"查看预填充的5个演示案例:

- Ti:Sapphire环形腔激光器对准
- Nd:YAG线性腔热效应问题排查
- OPO蝴蝶形腔参数优化
- 光纤激光器系统调试
- 锁模激光器稳定性测试

### 2. 创建新案例

1. 点击"新建案例"
2. 填写实验信息:
   - 标题
   - 描述
   - 腔型 (线性腔/环形腔/蝴蝶形腔/自定义)
   - 实验目标
   - 关键参数 (键值对)
   - 观察到的症状 (多选)
3. 点击"保存"

### 3. 生成AI辅助内容

在案例详情页面，切换到不同标签页并点击生成按钮:

- **实验计划**: 生成结构化的实验步骤
- **ReZonator模式**: 生成ReZonator模式/模板草稿
- **故障排查**: 基于症状生成排查建议
- **实验报告**: 生成实验报告模板

### 4. 上传附件

在"附件"标签页:
1. 选择文件上传
2. 查看已上传的附件
3. 下载或删除附件

## API端点

### 实验案例

- `POST /api/cases` - 创建案例
- `GET /api/cases` - 获取案例列表
- `GET /api/cases/{id}` - 获取案例详情
- `PUT /api/cases/{id}` - 更新案例
- `DELETE /api/cases/{id}` - 删除案例

### 内容生成

- `POST /api/cases/{id}/generate-plan` - 生成实验计划
- `POST /api/cases/{id}/generate-rezonator` - 生成ReZonator模式
- `POST /api/cases/{id}/generate-troubleshooting` - 生成故障排查
- `POST /api/cases/{id}/generate-report` - 生成实验报告
- `GET /api/cases/{id}/generated-contents` - 获取生成内容列表

### 附件

- `POST /api/cases/{id}/attachments` - 上传附件
- `GET /api/cases/{id}/attachments` - 获取附件列表
- `GET /api/attachments/{id}` - 下载附件
- `DELETE /api/attachments/{id}` - 删除附件

完整API文档: http://localhost:8000/docs

## 开发

### 后端开发

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 运行测试
pytest

# 运行开发服务器
uvicorn app.main:app --reload
```

### 前端开发

```bash
cd frontend

# 安装依赖
npm install

# 运行开发服务器
npm run dev

# 构建生产版本
npm run build
```

### 运行测试

```bash
# 后端测试
docker-compose exec backend pytest

# 或在本地
cd backend
pytest -v
```

## 配置

### 环境变量

后端环境变量 (backend/.env):

```env
DATABASE_URL=postgresql://laserclaw:laserclaw123@db:5432/laserclaw
UPLOAD_DIR=/app/uploads
MAX_UPLOAD_SIZE=10485760  # 10MB
AI_PROVIDER=mock  # mock, openai, anthropic (未来支持)
```

前端环境变量 (frontend/.env):

```env
VITE_API_URL=http://localhost:8000
```

## 数据库模式

### ExperimentCase (实验案例)

- `id`: 主键
- `title`: 标题
- `description`: 描述
- `cavity_type`: 腔型 (linear/ring/bow-tie/custom)
- `goal`: 实验目标
- `parameters`: 关键参数 (JSON)
- `symptoms`: 症状列表 (JSON)
- `created_at`: 创建时间
- `updated_at`: 更新时间

### GeneratedContent (生成内容)

- `id`: 主键
- `case_id`: 关联案例ID
- `content_type`: 内容类型 (plan/rezonator/troubleshooting/report)
- `content`: 内容 (JSON)
- `generated_at`: 生成时间

### Attachment (附件)

- `id`: 主键
- `case_id`: 关联案例ID
- `filename`: 文件名
- `filepath`: 文件路径
- `file_type`: 文件类型
- `uploaded_at`: 上传时间

## 路线图

### MVP (当前版本)

- ✅ 实验案例CRUD
- ✅ 结构化实验输入
- ✅ 实验计划生成
- ✅ ReZonator模式草稿生成
- ✅ 基于症状的故障排查
- ✅ 报告生成
- ✅ 附件管理
- ✅ 演示数据
- ✅ 模拟AI提供者

### 未来增强

- [ ] 真实AI提供者集成 (OpenAI, Anthropic)
- [ ] 高级多代理编排
- [ ] 用户认证和授权
- [ ] 协作功能
- [ ] 高级可视化
- [ ] 导出为多种格式
- [ ] 仪器驱动集成 (仅监控，非控制)
- [ ] 云部署支持
- [ ] 移动端适配

## 贡献

欢迎贡献! 请遵循以下步骤:

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 许可证

本项目采用 MIT 许可证 - 详见 LICENSE 文件

## 致谢

- ReZonator 社区
- 激光物理实验室的所有成员
- 所有贡献者

## 联系方式

- 项目主页: [GitHub Repository]
- 问题反馈: [GitHub Issues]

---

**[Fufan Lab]** - 让激光实验更简单
