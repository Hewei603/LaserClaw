# LaserClaw 中文说明

LaserClaw 是一个面向激光实验工作流的本地优先 **RAG Agent 工作台**。它把实验 Case 管理、实验室知识库索引、Case 专属证据检索、结构化 AI 生成、Agent 执行轨迹和协作治理整合在一个应用里。

> 安全说明：LaserClaw 不控制激光器、电源、位移台、联锁、光学平台、探测器或任何实验室硬件。AI 生成内容只作为辅助草稿，必须由具备资质的人员复核后才能用于真实实验。

![LaserClaw screenshot](https://github.com/user-attachments/assets/b8ebb7f4-f980-4671-8722-2ef0913f7f70)

## 解决什么问题

| 问题 | LaserClaw 的做法 |
|---|---|
| 实验知识分散在手册、SOP、笔记和附件里 | 使用两层 RAG 同时检索全局实验室文档和 Case 专属文档 |
| AI 回答难以审计 | 保存 retrieval run、citation、generated artifact、Agent step 和 tool call |
| 排障、计划、报告重复劳动多 | 自动生成结构化 plan、troubleshooting、report,几何参数由确定性物理内核计算 |
| 课题组需要长期协作 | 支持项目、用户、组、权限、知识库治理、prompt/workflow 版本和 Case bundle |

## 核心能力

- **Case-aware Agent chat**：持久化聊天会话，带上绑定 Case、最近对话、RAG 结果、citation 和检索置信度。
- **两层 RAG**：全局实验室知识作为共享依据，Case 附件和生成内容作为当前实验上下文。
- **全局知识库**：支持上传 PDF、TXT、Markdown、CSV、JSON、TSV、log 等共享文档。
- **知识库治理**：支持 source status、version、owner、reviewer、review time 和 reindex。
- **Tool-calling Agent 工作流**：自动路由普通聊天、实验计划、故障排查、实验报告和物理计算模块(谐振腔设计、相位匹配、镀膜评估、元件匹配、功率曲线)。
- **确定性物理内核**(纯 numpy):ABCD/高斯光束腔分析与**腔型设计搜索**(按实测热透镜裕度排序)、薄膜 TMM 镀膜评估、单轴/双轴相位匹配、功率曲线阈值与斜率效率拟合(含 Findlay-Clay / Caird 腔损耗反推)。实验计划里的几何与角度**是算出来的**,不是模型编的。
- **结构化元件库**:导入实验室元件清单(.xlsx),把镀膜/曲率/口径解析成结构化数据,按波长×功能做数据库级筛选,并针对需求逐参数判定(可用 / 需实测 / 淘汰,含非支配前沿)。腔型设计搜索只会推荐库里真有的镜子。
- **结构化 AI artifact**：保存 plan、troubleshooting、report、image analysis、物理模块结果等生成内容。
- **Prompt/workflow 版本管理**：维护 active prompt 和 workflow version，支持可复现 AI 运行。
- **Case bundle 导出**：导出完整 Case 包，包含 manifest、附件、生成内容和知识源元数据。
- **项目级 ACL**：Case、知识检索、附件、生成、Agent task、Case module 和 bundle export 都遵循项目权限。
- **RAG eval 与 benchmark**：提供脚本和 API，评估检索准确率、延迟、索引吞吐和 LLM JSON 可靠性。
- **检索后端**：支持确定性的 `sql_json`、Chroma、pgvector，以及可选 cross-encoder reranking。
- **Provider 支持**：MockProvider、OpenAI-compatible Chat Completions(OpenAI、DeepSeek、通义千问/DashScope、智谱 GLM、Moonshot Kimi)、Anthropic。
- **双语 UI**：支持中英文界面切换。

## 技术架构

```text
React + Vite 前端
  -> FastAPI 后端
      -> Case / attachment / knowledge / generation / agent / collaboration APIs
      -> SQLAlchemy models 和 Alembic migrations
      -> 本地 SQLite 或 Docker PostgreSQL/pgvector
      -> 文件上传和全局知识文档
      -> RAG 文档解析、切块、embedding、检索、citation
      -> 确定性物理内核(ABCD/高斯腔、薄膜 TMM、相位匹配、功率曲线拟合)—— 纯 numpy,不经过 LLM
      -> 结构化元件库(清单解析 + 逐参数评估器)
      -> OpenAI 兼容 / Anthropic / Mock provider
      -> 审计日志、usage、Agent trace、generated artifact
```

## RAG 工作流

```text
全局文档 / Case 附件 / 生成内容
  -> 文本抽取
  -> chunk 切分
  -> embedding
  -> KnowledgeSource + KnowledgeChunk
  -> 查询时检索
  -> RetrievalRun + RetrievalResult
  -> 带 citation 的上下文
  -> chat 或 artifact generation
```

LaserClaw 有两类检索来源：

1. **全局实验室知识**：安全手册、SOP、光学元件目录和实验室规则。所有 Case 都可以检索这类文档。
2. **Case 专属知识**：Case 数据、附件、图像分析、历史报告和生成内容，用于补充当前实验上下文。

![LaserClaw RAG screenshot](https://github.com/user-attachments/assets/ffc09e0d-93a4-4259-a07b-c943fbbf4cf9)

## Agent 工作流

```text
用户消息
  -> 创建或找到 chat session
  -> 保存 user message
  -> 判断意图
  -> 根据聊天历史、Case 数据、RAG 结果和 citations 构造上下文
  -> 返回聊天回复或创建正式 Agent task
  -> 保存 assistant message / task / artifact / citations
```

普通聊天时，后端会把结构化上下文交给模型回答。生成 artifact 时，系统会创建 `AgentTask`，生成步骤，调用工具，检索证据，生成内容，保存到 Case，并保留完整执行轨迹。

## 检索选项

默认 RAG 栈是确定性的本地实现：

- tokenization：ASCII 词项，加中文字符、bigram、trigram
- 常见安全和光学术语的 synonym expansion
- 按 `[SAF-PPE]`、`[SAF-SOP]`、`[OPT-MIRROR]` 等标题做 section-aware chunking
- chunk 上保存 section metadata
- 对安全和光学相关查询做轻量 domain boost

生产取向的检索后端也已经接入：

- `sql_json`：基于 JSON embedding 和词法评分的本地 fallback
- `chroma`：带本地持久化 collection 的 dense vector retrieval
- `pgvector`：PostgreSQL/pgvector 检索，SQL metadata 仍然是权威来源
- 可选 `sentence_transformers` cross-encoder reranker，只对有限候选集重排

操作和验收细节见 [docs/RAG_OPERATIONS.md](docs/RAG_OPERATIONS.md)。

## 当前评测证据

下面每个数字都可以用旁边的命令在本仓库复现,配置为**默认本地配置**
(`EMBEDDING_PROVIDER=local`、`RETRIEVAL_BACKEND=sql_json`、`AI_PROVIDER=mock`)。
测量时间 2026-07-26。每条命令都会把 JSON 报告写到 `docs/benchmarks/`,该目录**已 gitignore**
——因为报告可能索引到私有实验室文档,所以请在本地自行重跑生成,而不是依赖仓库里的副本。

检索语料是**合成的**(不是真实实验室制度、设备数据或安全培训材料),而且规模很小
(3 个文档源、5 个分块、10 条带标注的查询)。因此这些检索数字只说明**流程是通的**,
**不是**对生产规模准确率的声明。

| 检查项 | 结果 | 复现命令 |
|---|---|---|
| 后端测试套件 | 292 passed, 2 skipped | `cd backend && py -m pytest -q` |
| 物理内核对拍(解析解/文献值) | 已含在上面(TMM 与独立的 `tmm` 库对拍至机器精度) | `py -m pytest tests/test_physics_*.py -q` |
| 意图路由用例 | 57 passed | `py -m pytest tests/test_router.py -q` |
| RAG 数据集断言 | 8 passed(37 条查询数据集) | `py -m pytest tests/eval_rag_dataset.py -q` |
| Agent 轨迹完整性 | 7 passed | `py -m pytest tests/eval_agent_trace.py -q` |
| API 鉴权依赖审计 | 74 条 `/api/*` 路由,0 findings | `py scripts/audit_endpoint_acl.py` |
| 前端 lint/build | 通过 | `cd frontend && npm run lint && npm run build` |

合成语料上的检索质量与延迟
(报告:`docs/benchmarks/resume_metrics_*.json`):

| 指标 | 结果 |
|---|---:|
| Recall@1 | 90.00% |
| Recall@3 | 100.00% |
| Recall@5 | 100.00% |
| MRR | 0.95 |
| 查询延迟 p50 / p95 | 12.7 ms / 14.4 ms |
| 索引吞吐 | 103.9 块/秒 |

复现:`py scripts/benchmark_resume_metrics.py --repeats 3 --skip-llm`
(10 条标注查询 × 3 轮 = 30 次查询,top_k=5)。

结构化生成的输出形状与延迟(MockProvider,
`docs/benchmarks/latest_generation_latency.json`):

| 模式 | 次数 | Schema 通过率 | p50 延迟 |
|---|---:|---:|---:|
| plan | 3 | 100% | 658 ms |
| troubleshooting | 3 | 100% | 47 ms |
| report | 3 | 100% | 46 ms |

复现:`py scripts/benchmark_generation_latency.py --repeats 3`。
这里的延迟是确定性模板路径;接真实模型后延迟由模型主导
(用 `gpt-5` 生成一份实验计划约需 60–120 秒)。

其他 benchmark 脚本:

- `backend/scripts/benchmark_retrieval_backends.py`:配好 pgvector 数据库后,对比 `sql_json`、Chroma、pgvector。
- `backend/scripts/eval_authorized_rag.py`:在授权的私有语料上评测检索。

已知限制:

- 公开语料是合成的且规模很小;引用任何检索数字前请在你自己的语料上重测。
- 本地词法检索不能替代生产级 embedding 或 reranking。
- 上面的生成 benchmark 用的是 MockProvider,衡量的是 schema 形状与链路,不是模型质量。
- 物理结果是确定性的且有单元测试,但**纸面上稳定的腔不等于一定能出光**:泵浦模式重叠、镀膜损耗、对准质量仍然决定成败。

## Windows 快速启动

**前置要求**(只需装一次):

- [Python 3.11+](https://www.python.org/downloads/) —— 安装时勾选 "Add python.exe to PATH"
- [Node.js 22 LTS](https://nodejs.org/)

然后双击:

```bat
Launch-LaserClaw.bat
```

首次运行会自动创建 `.env` 配置文件(演示模式)。**日常怎么用请看中文使用指南:[docs/GUIDE_V2.md](docs/GUIDE_V2.md)**。

启动脚本会安装依赖并启动:

- 后端 API：<http://127.0.0.1:8000>
- 前端：<http://127.0.0.1:5173>
- Agent 工作台：<http://127.0.0.1:5173/agent>
- API 文档：<http://127.0.0.1:8000/docs>

## 手动本地启动

后端：

```powershell
cd backend
py -m pip install -r requirements.txt
py -m alembic upgrade head
py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

## Docker

默认 Compose 文件面向生产形态：后端不使用 reload，前端构建为静态文件并由 nginx 服务。

```bash
docker compose up -d --build
```

服务地址：

- 前端：<http://localhost:5173>
- 后端 API：<http://localhost:8000>
- API 文档：<http://localhost:8000/docs>

如果需要带热更新的开发模式：

```bash
docker compose -f docker-compose.dev.yml up -d --build
```

停止：

```bash
docker compose down
docker compose -f docker-compose.dev.yml down
```

部署和 release gate 细节见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)，当前验收矩阵见 [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)。

## 环境变量

创建 `.env` 配置本地 provider 和运行参数。不要提交真实 API key。

```env
AI_PROVIDER=mock
STRICT_PROVIDER=false

OPENAI_API_KEY=
OPENAI_MODEL=gpt-5
OPENAI_BASE_URL=https://api.openai.com/v1

ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-5

# 国内模型厂商(推荐):AI_PROVIDER 填厂商名 + 对应 key
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
QWEN_API_KEY=
QWEN_MODEL=qwen-plus
ZHIPU_API_KEY=
ZHIPU_MODEL=glm-4-plus
MOONSHOT_API_KEY=
MOONSHOT_MODEL=moonshot-v1-8k

DATABASE_URL=sqlite:///./laserclaw.db
UPLOAD_DIR=./uploads
MAX_UPLOAD_SIZE=52428800
AUTO_CREATE_TABLES=true

EMBEDDING_PROVIDER=local
RETRIEVAL_BACKEND=sql_json
VECTOR_STORE_DIR=./vector_store
DOCKER_VECTOR_STORE_DIR=/app/vector_store
PGVECTOR_DIMENSION=384
RERANKER_PROVIDER=none

REQUIRE_AUTH=false
API_KEY=

VITE_API_URL=http://127.0.0.1:8000
```

Provider 模式：

- `mock`：确定性的本地 demo 模式(输出为固定模板,页面顶部会显示演示模式横幅)
- `deepseek` / `qwen` / `zhipu` / `moonshot`：国内模型厂商(DeepSeek、通义千问、智谱 GLM、Kimi),填对应 `*_API_KEY` 即可
- `openai`：OpenAI-compatible Chat Completions provider
- `anthropic`：Anthropic provider

严格评测时建议设置 `STRICT_PROVIDER=true`，这样真实 Provider 不可用时会明确失败，而不是回退到 MockProvider。

## 质量检查

后端测试：

```powershell
cd backend
py -m pytest tests -q
```

后端 lint：

```powershell
py -m pip install -r backend\requirements-dev.txt
py -m ruff check backend
```

前端 lint 和构建：

```powershell
cd frontend
npm ci
npm run lint
npm run build
```

本地一键验收：

```powershell
cd backend
py scripts\acceptance_check.py
```

Hosted CI 和私有 eval 证据可用后，运行最终 release audit：

```powershell
cd backend
py scripts\final_acceptance_audit.py
```

## Benchmark

运行可复现 benchmark：

```powershell
py backend\scripts\benchmark_resume_metrics.py --repeats 10 --top-k 5
```

跳过真实 LLM 调用：

```powershell
py backend\scripts\benchmark_resume_metrics.py --repeats 10 --top-k 5 --skip-llm
```

授权私有文档 eval 使用 `docs/evals/private/` 下的 JSONL 文件，该目录默认不提交到 Git：

```powershell
cd backend
py scripts\index_authorized_docs.py
py scripts\eval_authorized_rag.py --dataset ..\docs\evals\private\rag_eval_authorized_holdout.jsonl --top-k 5 --min-positive-hit-rate 0.85 --min-negative-rejection-rate 0.90
py scripts\tune_retrieval_thresholds.py --dataset ..\docs\evals\private\rag_eval_authorized.jsonl --top-k 5
```

## 主要 API

- `POST /api/cases`
- `GET /api/cases`
- `GET /api/cases/{case_id}`
- `GET /api/cases/{case_id}/bundle`
- `POST /api/cases/{case_id}/attachments`
- `POST /api/cases/{case_id}/generate-plan`
- `POST /api/cases/{case_id}/generate-troubleshooting`
- `POST /api/cases/{case_id}/generate-report`
- `POST /api/knowledge/sources/upload`
- `GET /api/knowledge/sources`
- `PATCH /api/knowledge/sources/{source_id}/governance`
- `POST /api/knowledge/search`
- `POST /api/agent/chat`
- `POST /api/agent/tasks`
- `GET /api/agent/tasks/{task_id}`
- `POST /api/collaboration/users`
- `POST /api/collaboration/groups`
- `POST /api/collaboration/projects`
- `POST /api/versioning/prompts`
- `POST /api/versioning/workflows`
- `POST /api/evals/rag`
- `POST /api/evals/rag/private-dataset`
- `POST /api/cases/{case_id}/modules`
- `POST /api/cases/modules/{module_id}/run`
- `GET /api/cases/{case_id}/components`
- `GET /api/cases/{case_id}/components/procurement.csv`
- `POST /api/inventory/import`
- `GET /api/inventory/items`
- `GET /api/inventory/sources`
- `DELETE /api/inventory/items`
- `POST /api/inventory/match`

## 项目结构

```text
LaserClaw/
|-- backend/
|   |-- app/
|   |   |-- agent/          # context, routing, planner, orchestrator, tools
|   |   |-- api/            # FastAPI routes
|   |   |-- auth/           # API-key auth, roles, project-level ACL
|   |   |-- evals/          # 检索评测数据集与指标
|   |   |-- inventory/      # 元件清单解析、导入、逐参数评估器
|   |   |-- knowledge/      # 文档解析、切块、embedding、检索
|   |   |-- models/         # SQLAlchemy 模型
|   |   |-- observability/  # 审计与 usage 记账
|   |   |-- physics/        # 确定性物理内核:ABCD/高斯、TMM、相位匹配、
|   |   |                   #   腔型设计搜索、功率曲线拟合(纯 numpy)
|   |   |-- providers/      # Mock、OpenAI 兼容(OpenAI/DeepSeek/通义/智谱/Kimi)、Anthropic
|   |   `-- schemas/
|   |-- alembic/
|   |-- scripts/
|   |-- tests/
|   |-- requirements.txt
|   `-- requirements-dev.txt
|-- frontend/
|   |-- src/
|   |   |-- api/
|   |   |-- components/
|   |   |-- pages/
|   |   |-- LanguageContext.jsx
|   |   `-- i18n.js
|   |-- Dockerfile
|   |-- Dockerfile.dev
|   `-- package.json
|-- docs/
|-- docker-compose.yml
|-- docker-compose.dev.yml
|-- pyproject.toml
|-- Launch-LaserClaw.bat
|-- README.md
`-- READMEcn.md
```

## 当前限制

- API-key authentication 适合本地和小范围可信部署；多人生产部署应接入更强的身份认证，并由服务端签发用户上下文。
- pgvector 和 Chroma 路径已经实现，但生产规模能力需要按目标部署配置运行文档中的集成检查。
- Cross-encoder reranking 可用，但默认关闭，因为它会增加延迟和模型依赖。
- Benchmark 默认使用 synthetic evaluation documents，除非替换为授权的真实实验室文档。
- AI 生成内容只能作为辅助草稿，不能替代正式安全制度、SOP 或人工判断。

## License

MIT License。详见 [LICENSE](LICENSE)。
