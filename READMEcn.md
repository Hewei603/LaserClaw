# LaserClaw 中文说明

LaserClaw 是一个面向激光实验工作流的本地优先 **RAG Agent 工作台**。它把实验 Case 管理、全局实验室知识库、Case 专属文档检索、结构化 AI 生成、Agent 执行轨迹和课题组协作治理整合在一个应用里。

> 安全说明：LaserClaw 不控制激光器、电源、位移台、联锁、光学平台、探测器或任何实验室硬件。所有 AI 生成内容都只是辅助草稿，必须由具备资质的人员复核后才能用于真实实验。

## 解决什么问题

| 问题 | LaserClaw 的做法 |
|---|---|
| 实验知识分散在手册、SOP、笔记和附件里 | 用两层 RAG 同时检索全局实验室文档和 Case 文档 |
| AI 回答难以审计 | 保存 retrieval run、citation、generated artifact、Agent step 和 tool call |
| 排障、计划、报告和仿真草稿重复劳动多 | 自动生成结构化 plan、troubleshooting、report、ReZonator draft |
| 课题组需要长期协作 | 支持项目、用户、组、权限、知识库治理、prompt/workflow 版本和 Case bundle |

## 核心能力

- **Case-aware Agent chat**：聊天会带上最近对话历史、绑定 Case、RAG 检索结果、citation 和检索置信度。
- **两层 RAG**：全局实验室文档作为实验室级规则和公共知识；Case 附件、图片分析和生成内容作为当前实验上下文。
- **全局知识库**：支持上传 PDF、TXT、Markdown、CSV、JSON、TSV、log 等共享文档，供所有 Case 检索。
- **Case schema v2**：支持项目归属、状态、可见性、标签、测量数据、安全备注、结论、owner 和 schema version。
- **知识库治理**：支持 `draft`、`approved`、`deprecated`、`archived` 状态，以及 version、owner、reviewer、review time 和 reindex。
- **Tool-calling Agent 工作流**：自动区分普通聊天、实验计划、故障排查、实验报告和 ReZonator 草稿。
- **结构化 AI artifact**：保存 plan、troubleshooting、report、image analysis、resonator 等生成内容。
- **Prompt/workflow 版本管理**：可以维护 active prompt 和 workflow version，支持可复现 AI 运行。
- **Case bundle 导出**：导出完整 Case 包，包含 manifest、附件、生成内容和知识源 metadata。
- **RAG eval 和 benchmark**：提供可复现脚本/API，评测检索准确率、延迟、索引吞吐和 LLM JSON 可靠性。
- **多 Provider 支持**：MockProvider、OpenAI-compatible Chat Completions、Anthropic。
- **双语 UI**：支持中英文界面切换。

## 技术架构

```text
React + Vite 前端
  -> FastAPI 后端
      -> Case / attachment / knowledge / generation / agent / collaboration APIs
      -> SQLAlchemy models
      -> 本地 SQLite 或 Docker PostgreSQL
      -> 文件上传和全局知识文档
      -> RAG 文档解析、切块、embedding、检索、citation
      -> OpenAI / Anthropic / Mock provider
      -> 审计日志、token/usage、Agent trace、generated artifact
```

## RAG 工作流

```text
全局 PDF / Case 附件 / 生成内容
  -> 文本抽取
  -> chunk 切分
  -> embedding
  -> KnowledgeSource + KnowledgeChunk
  -> 查询时检索
  -> RetrievalRun + RetrievalResult
  -> 带 citation 的上下文
  -> chat 或 artifact generation
```

LaserClaw 的 RAG 有两类检索源：

1. **全局实验室知识**：安全手册、SOP、光学元件目录、实验室规则等。所有 Case 都会检索这类文档，并且它们在安全和规范问题上优先级最高。
2. **Case 专属知识**：Case 本身、附件、图片分析、历史报告和生成内容。它们用于补充当前实验的局部上下文。

## Agent 工作流

```text
用户消息
  -> 创建或找到 chat session
  -> 保存 user message
  -> 判断意图
  -> 构造上下文：
       当前消息
       最近聊天历史
       绑定 Case 数据
       全局 RAG 结果
       Case RAG 结果
       citations 和 retrieval confidence
  -> 普通聊天回复或创建正式 Agent task
  -> 保存 assistant message / task / artifact / citations
```

普通聊天时，后端会把结构化 context 交给模型回答。生成 artifact 时，系统会创建 `AgentTask`，生成步骤，调用工具，检索证据，生成内容，保存到 Case，并保存完整执行轨迹。

## Windows 快速启动

```bat
Launch-LaserClaw.bat
```

启动脚本会安装依赖并启动：

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

## Docker Compose

```bash
docker compose up -d --build
```

服务地址：

- 前端：<http://localhost:5173>
- 后端 API：<http://localhost:8000>
- API 文档：<http://localhost:8000/docs>

停止：

```bash
docker compose down
```

## 环境变量

创建 `.env` 配置本地 provider 和运行参数。不要提交真实 API key。

```env
AI_PROVIDER=mock
STRICT_PROVIDER=false

OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o
OPENAI_BASE_URL=https://api.openai.com/v1

ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-5

DATABASE_URL=sqlite:///./laserclaw.db
UPLOAD_DIR=./uploads
MAX_UPLOAD_SIZE=52428800
AUTO_CREATE_TABLES=true

EMBEDDING_PROVIDER=local
RETRIEVAL_BACKEND=sql_json
VECTOR_STORE_DIR=./vector_store

REQUIRE_AUTH=false
API_KEY=

VITE_API_URL=http://127.0.0.1:8000
```

Provider 模式：

- `mock`：确定性的本地 demo 模式
- `openai`：OpenAI-compatible Chat Completions Provider
- `anthropic`：Anthropic Provider

严格评测时建议设置 `STRICT_PROVIDER=true`，这样真实 Provider 不可用时会明确失败，而不是回退到 MockProvider。

## Benchmark

运行可复现 benchmark：

```powershell
py backend\scripts\benchmark_resume_metrics.py --repeats 10 --top-k 5
```

跳过真实 LLM 调用：

```powershell
py backend\scripts\benchmark_resume_metrics.py --repeats 10 --top-k 5 --skip-llm
```

报告会在本地生成，不提交到 Git：

```text
docs/benchmarks/
```

## 测试

```powershell
cd backend
py -m pytest tests -q
```

当前本地结果：

```text
127 passed
```

前端构建：

```powershell
cd frontend
npm run build
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
- `POST /api/cases/{case_id}/generate-rezonator`
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

## 关键数据表

- `experiment_cases`
- `attachments`
- `knowledge_sources`
- `knowledge_chunks`
- `retrieval_runs`
- `retrieval_results`
- `agent_chat_sessions`
- `agent_chat_messages`
- `agent_tasks`
- `agent_steps`
- `agent_tool_calls`
- `generated_contents`
- `organizations`
- `users`
- `groups`
- `projects`
- `prompt_versions`
- `workflow_versions`
- `rag_eval_runs`
- `audit_logs`

## 项目结构

```text
LaserClaw/
|-- backend/
|   |-- app/
|   |   |-- agent/          # context, routing, planner, orchestrator, tools
|   |   |-- api/            # FastAPI routes
|   |   |-- auth/           # API-key auth and coarse roles
|   |   |-- knowledge/      # ingestion, chunking, embeddings, retrieval
|   |   |-- models/         # SQLAlchemy models
|   |   |-- observability/  # audit and usage accounting
|   |   |-- providers/      # Mock, OpenAI, Anthropic
|   |   `-- schemas/
|   |-- alembic/
|   |-- scripts/
|   |-- tests/
|   `-- requirements.txt
|-- frontend/
|   |-- src/
|   |   |-- api/
|   |   |-- pages/
|   |   |-- LanguageContext.jsx
|   |   `-- i18n.js
|   `-- package.json
|-- docs/
|-- Launch-LaserClaw.bat
|-- docker-compose.yml
|-- README.md
`-- READMEcn.md
```

## 当前限制

- 用户/组/项目模型已经具备，但 endpoint 级细粒度权限还需要继续加强。
- 大规模检索应接入向量索引后再宣称生产级延迟。
- 长对话目前使用最近消息窗口，还没有自动长期记忆总结。
- Benchmark 默认使用 synthetic evaluation documents，除非替换为有授权的真实实验室文档。
- AI 生成内容只能作为辅助草稿，不能替代真实安全制度、SOP 或人工判断。

## License

MIT License。详见 [LICENSE](LICENSE)。
