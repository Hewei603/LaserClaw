# LaserClaw 架构与工作流说明

> 本文描述 LaserClaw 的整体架构、各层职责、核心工作流,并标注每个环节对应的源码文件,便于对照阅读代码。
> 设计哲学一句话:**物理量由确定性内核计算,LLM 只在算好的事实之上做取舍和解释,人做最终仲裁。**

---

## 1. 系统总览

LaserClaw 是一个面向激光实验室的本地优先(local-first)实验管理 + RAG + Agent 平台:

- **实验 Case 管理**:实验目标、参数、症状、测量、附件、生成产物,全部持久化可审计。
- **两级 RAG 知识库**:全局实验室文档(SOP/目录)+ Case 级证据,检索带引用与置信度。
- **Agent 工作流**:中文/英文自然语言 → 意图路由 → 计划 → 工具调用 → 产物入库(全程留痕)。
- **确定性物理内核**:谐振腔 ABCD/高斯、薄膜 TMM、相位匹配——Agent 的"计算器",不靠 LLM 猜数。
- **结构化元件库(L0)+ 逐参数评估器(L1)**:实验室真实库存 xlsx → 类型化数据 → 可裁决的选型判定。

```
前端 React ──► FastAPI 路由层 ──► 权限/ACL ──► 业务层
                                        │
        ┌───────────────┬───────────────┼───────────────┬──────────────┐
        ▼               ▼               ▼               ▼              ▼
   Agent 编排      RAG 知识层      物理内核(纯)     库存 L0/L1      LLM Provider
  (计划/工具/留痕) (切块/嵌入/检索)  (ABCD/TMM/相位匹配) (解析/导入/判定)  (mock/openai/anthropic)
        └───────────────┴───────┬───────┴───────────────┘
                                ▼
                    SQLAlchemy 模型 + Alembic 迁移 (SQLite/PostgreSQL)
```

---

## 2. 目录总图(按层)

| 层 | 目录/文件 | 职责 |
|---|---|---|
| 入口 | `backend/app/main.py` | FastAPI 应用、路由挂载、CORS、request-id 中间件 |
| 配置 | `backend/app/config.py` | 全部环境变量(provider、检索后端、阈值、ACL 开关) |
| 数据库 | `backend/app/database.py` | engine/session,`get_db()` 异常回滚 |
| API 路由 | `backend/app/api/` | 每个文件一个领域(见 §3) |
| 权限 | `backend/app/auth/` | principal 解析 + 项目级 ACL |
| Agent | `backend/app/agent/` | 意图路由、计划、编排、工具、上下文、记忆 |
| RAG | `backend/app/knowledge/` | 提取→切块→嵌入→向量库→检索→重排 |
| 物理内核 | `backend/app/physics/` | 纯 numpy 确定性计算(见 §5) |
| 库存 | `backend/app/inventory/` | L0 解析/导入 + L1 评估(见 §6) |
| Provider | `backend/app/providers/` | LLM 抽象:mock / openai / anthropic |
| 模型 | `backend/app/models/` | SQLAlchemy ORM(见 §8) |
| 迁移 | `backend/alembic/versions/` | 线性迁移链 0001→0008 |
| 观测 | `backend/app/observability/` | 审计日志、token 用量 |
| 评测 | `backend/app/evals/` | RAG 检索评测指标与验收门 |
| 测试 | `backend/tests/` | 237+ 用例(见 §9) |
| 演示 | `backend/scripts/demo_*.py` | 端到端可复现演示(见 §10) |
| 前端 | `frontend/src/` | React 页面 + API 客户端 |

---

## 3. API 路由层(`backend/app/api/`)

挂载点见 `backend/app/main.py`(`include_router` 段)。

| 前缀 | 文件 | 职责 |
|---|---|---|
| `/api/cases` | `api/cases.py` | Case CRUD、打包导出(bundle) |
| `/api/cases`(模块) | `api/case_modules.py` | Case 模块:创建/上传文件/**运行**(稳定性、光谱、光斑、元件清单、**cavity_design / phase_match / coating_tmm / component_match / power_curve**);运行分发在 `run_case_module` 的 if/elif 链。测量数据(功率曲线 CSV、光谱数据与示波器截图、光斑图)以 `CaseModuleFile` 挂在对应模块上 |
| `/api/cases`(生成) | `api/generation.py` | LLM 生成:计划/排故/报告(带 RAG 增强)。**实验计划先跑确定性物理内核**(`physics/case_context.py`),把算出的腔长/束腰/摆位/相位匹配角作为权威数值注入提示词 |
| `/api/attachments` | `api/attachments.py` | Case 附件上传/下载(带 ACL) |
| `/api/knowledge` | `api/knowledge.py` | 全局知识源上传、治理状态、`/search` 检索(带 ACL 过滤) |
| `/api/agent` | `api/agent.py` | **聊天入口**(`/chat`,含 `_route_mode` 意图路由)、任务(`/tasks`)、会话/记忆 |
| `/api/inventory` | `api/inventory.py` | **元件库**:`/import`(xlsx 导入)、`/items`(类型化过滤)、`/match`(L1 匹配) |
| `/api/collaboration` | `api/collaboration.py` | 用户/项目/组/成员管理(admin) |
| `/api/versioning` | `api/versioning.py` | Prompt/Workflow 版本管理 |
| `/api/evals` | `api/evals.py` | RAG 检索评测运行(reviewer 权限 + 租户过滤) |
| `/api/admin` | `api/admin.py` | 审计日志、用量查询(admin) |

---

## 4. 权限与多租户(`backend/app/auth/`)

- `auth/security.py` — `get_current_principal`:身份解析。**权限以数据库 `User.role` 为准**
  (`X-User-Id` 对应真实用户时,请求头的 role 不生效,防伪造提权);未注册 id 走演示引导路径;
  `REQUIRE_AUTH=true` 时未知/停用用户直接拒绝。
- `auth/acl.py` — 项目级 ACL:`can_view/edit/delete_case`、`accessible_case_ids`(检索过滤)、
  `can_manage_knowledge`(reviewer/admin 门)。
- 检索侧 ACL:`api/knowledge.py::search` 与 `api/evals.py` 都将 `accessible_case_ids` 传入
  `knowledge/retrieval.py`,防止跨租户内容泄漏。

---

## 5. 物理内核(`backend/app/physics/`)——确定性计算层

**纯 numpy + 标准库,不依赖 web/DB/LLM,离线确定性,可独立复用。** 全部公式为教科书清洁室实现
(Kogelnik & Li、Siegman、Born & Wolf、Macleod、Boyd/Dmitriev);ReZonator 2 源码仅作仓库外参考
oracle(GPL,已 gitignore,绝不拷贝)。

| 文件 | 内容 | 验证方式 |
|---|---|---|
| `physics/materials.py` + `physics/data/materials.json` | 28 种材料色散(Sellmeier/Cauchy),每条带出处+置信度+适用波段 | 25 个文献折射率基准点(`tests/test_physics_materials.py`) |
| `physics/tmm.py` | 薄膜特征矩阵求解 R/T/A(s/p、任意入射角、复折射率吸收) | 解析解(Fresnel、四分之一波 AR、(HL)ᴺ 闭式)+ **与 Byrnes `tmm` 库 200 随机膜系对拍至机器精度**(`tests/test_physics_tmm.py`、`tests/test_physics_tmm_oracle.py`) |
| `physics/archetypes.py` | 标称镀膜的"诚实原型":QWOT 阻带区间、对比度括号、AOI 蓝移、s/p 实测分裂 | `tests/test_physics_coating_tool.py` |
| `physics/coating_tool.py` | 镀膜评估统一入口 `evaluate_coating`:精确膜系 / 厂商曲线 / 标称原型三模式 | 同上 + 对抗回归(`tests/test_physics_adversarial_fixes.py`) |
| `physics/beam.py` | ABCD 元件矩阵、高斯 q 传播、往返稳定性、自洽本征模、各面光斑(= ReZonator 级内核) | 对称腔/平凹腔/共焦极限闭式解(`tests/test_physics_beam.py`) |
| `physics/nonlinear.py` | 单轴+双轴主平面相位匹配(所有偏振配对)、走离 | 文献角度:BBO SHG-I 22.8°、THG 31.3°、LBO 11.4°、BiBO 等(`tests/test_physics_nonlinear.py`) |
| `physics/toolkit.py` | **工作流适配层**(dict→dict):`run_cavity_design`(定长分析/腔长扫描→稳区→推荐几何+元件摆位,未给目标束腰时按**实测热透镜裕度**排序而非 \|m\| 代理;腔长留空默认扫 30–800mm)、`run_phase_match`(接受案例参数别名 `nonlinear_crystal`/`wavelength_nm`/`shg_pm_type`,增益晶体字典不会被误当晶体名)、`run_coating_tmm`;所有 needs_input/failed 提示为中文;REST 与 Agent 共用 | `tests/test_physics_modules.py`、`tests/test_grad_student_ux_fixes.py` |
| `physics/design.py` | **腔型设计搜索**:用户没给镜子时,遍历候选曲率×腔长,两级排序输出可搭建几何——先按束腰匹配粗筛,再对入围者**实测热透镜裕度**(在增益介质处插薄透镜、扫光焦度直至失稳),`score = 0.55×模式惩罚 + 0.45×热稳健性惩罚`;候选曲率优先取自实验室库存 | `tests/test_physics_grounded_plan.py` |
| `physics/case_context.py` | **案例→物理事实桥接**:实验计划生成前先跑内核(已知几何→分析;未知几何→设计搜索;非线性→相位匹配;标称镀膜→阻带核查),结果作为权威数值注入提示词 | 同上 |
| `physics/laser_metrics.py` | **测量分析**:功率曲线阈值+斜率效率拟合(自动线性区检测)、Findlay-Clay / Caird 跨曲线腔损耗分析 | 合成数据还原真值(`tests/test_power_curve.py`) |
| `physics/units.py` / `physics/constants.py` | 单位约定(波长 nm、光学长度 mm、膜厚 nm)与常数 | — |

> 曾由对抗式物理审查(5 个独立视角)发现并修复一个关键分支错误(`_cos_theta` 在 n-ik 约定下
> 选反,导致吸收基底 R>1);所有确认项均有回归测试锁定:`tests/test_physics_adversarial_fixes.py`。

---

## 6. 元件库 L0/L1(`backend/app/inventory/`)

把"选元件"从文本相似度升级为**可裁决的结构化判定**:

| 文件 | 层 | 内容 |
|---|---|---|
| `inventory/parser.py` | L0 | 镀膜字符串语法解析:面标记(S1/S2)、功能(HR/AR/HT/`T=x%`→PR)、阈值(`R>99.5%`)、波段(`1064-1066`)、多波长(`880&1053+1314`、`914/517`)、全角归一(NFKC)、裸波长归组;几何(`R=-100`/平镜/`D=25.4mm`/`3*3*5mm3`/`θ=159.6°`/c-cut/掺杂);**未知/损坏标记显式保留,不猜** |
| `inventory/importer.py` | L0 | xlsx 工作簿 → `InventoryItem` + 每面×每波段 `CoatingSpec` 行;前向填充组;导入报告含**待复核队列**(parse_confidence != parsed) |
| `inventory/evaluator.py` | L1 | 需求 spec → 逐参数判定档案(**不压成单一分数**):连续量硬门+裕度(曲率/口径)、**标称波长三态**(design_match / maybe_usable / off,off-design 走 `physics/archetypes` 阻带先验)、功能族规则(同面相反功能=conflict 否决)、未知→must_measure;硬伤一票否决;幸存者**支配排序**输出非支配前沿 |
| `models/inventory.py` | — | 两张表定义;迁移:`alembic/versions/20260724_0008_structured_inventory.py` |
| `api/inventory.py` | — | `/import`(reviewer 门,幂等按来源文件替换)、`/items`(SQL 级波长×功能过滤)、`/match`(L1) |

判定档案示例字段:`hard_violations / parameters.coatings[].status / unknowns / must_measure / frontier`。
"maybe_usable" 一律注明依据(原型阻带区间)并列入实测清单——**标签不是曲线,系统不假装知道**。

---

## 7. Agent 层(`backend/app/agent/`)与核心工作流

### 7.1 组件

| 文件 | 职责 |
|---|---|
| `api/agent.py` | `/chat` 入口;`_route_mode`(意图词 `_GENERATE_INTENT` × 内容词 `_CONTENT_KEYWORDS` 双命中才路由,否则纯聊天);会话管理 |
| `agent/planner.py` | 确定性 4 步计划(模块类:读上下文→查输入→跑工具→存结果) |
| `agent/orchestrator.py` | `create_and_run_task`:建任务→建步骤→依计划执行;`MODULE_MODES` 决定走工具分支;物理模式经 `record_tool_call` **真正执行计算**;失败路径整体回滚后落干净的 failed 任务 |
| `agent/tools.py` | 工具注册表 `tool_schemas()`、审计包装 `record_tool_call`(输入/输出/延迟/状态入库)、各工具 payload(含 `run_physics_tool_payload`) |
| `agent/context.py` | 聊天上下文组装:历史+滚动摘要+记忆+两级 RAG |
| `agent/memory.py` | 会话摘要与长期记忆条目 |
| `agent/guardrails.py` | 目标风险粗评(risk_level) |

### 7.2 一次"设计谐振腔"请求的完整时序

```
用户: "帮我设计一个谐振腔,扫描腔长找到稳区,算出束腰和元件摆放位置"
  │
  ▼ api/agent.py::/chat  →  _route_mode() → "cavity_design"
  ▼ agent/orchestrator.py::create_and_run_task(mode=cavity_design)
      步骤1 get_case / list_attachments / list_generated_contents   (agent/tools.py)
      步骤2 search_knowledge → knowledge/retrieval.py 两级检索,带引用
      步骤3 compute_cavity_design                                    (record_tool_call 留痕)
             └► physics/toolkit.py::run_cavity_design
                 └► physics/beam.py: 逐腔长 ABCD 往返矩阵 → 稳定性 |m|<1
                    → 自洽本征 q → 束腰/各面光斑 → 稳区窗口
                    → 推荐 L(给了目标束腰按束腰匹配;否则按实测热透镜裕度最大)
      步骤4 save_generated_content → GeneratedContent(带 citations) → 入 RAG 索引
  ▼ 全程 AgentTask/AgentStep/AgentToolCall/RetrievalRun 落库,可回放审计
```

配置来源:**Case.parameters 打底,模块 config_json 覆盖**(orchestrator 物理分支),
所以实验参数随 Case 持久化,Agent 不需要重复要参数。

### 7.3 元件匹配请求(component_match)

```
"帮我从库存里选一块 1064 的 HR 镜" → _route_mode → "component_match"
  → orchestrator: match_components 工具
  → inventory/evaluator.py::evaluate_candidates(db, requirement)
      逐件: 硬门(曲率/口径/数量/损坏) → 镀膜三态(接 physics 阻带先验) → 判定档案
      → 硬伤淘汰 + 支配排序 → 非支配前沿 + 淘汰原因分布 + must_measure 清单
```

---

## 8. 数据模型(`backend/app/models/`)与迁移

| 文件 | 表 |
|---|---|
| `models/experiment_case.py` | `experiment_cases`(参数/症状/测量/可见性) |
| `models/case_module.py` | `case_modules` / `case_module_files` / `case_component_items` |
| `models/agent.py` | `agent_tasks` / `agent_steps` / `agent_tool_calls` / 会话 / 记忆 |
| `models/knowledge.py` | `knowledge_sources` / `knowledge_chunks` / `retrieval_runs` / `retrieval_results` |
| `models/inventory.py` | `inventory_items` / `coating_specs` |
| `models/user.py` | 组织/用户/组/项目/成员(ACL 基础) |
| `models/generated_content.py` `models/attachment.py` `models/audit.py` `models/versioning.py` | 产物/附件/审计/版本/评测 |

迁移链(线性,`backend/alembic/versions/`):
`20260515_0001` → `0002` → `0003` → `0004` → `0005(pgvector)` → `0006(agent memory)` → `0007(case modules)` → **`20260724_0008(structured inventory)`**。

RAG 管线文件:`knowledge/ingestion.py`(提取/入库)→ `knowledge/chunking.py` → `knowledge/embeddings.py`
(local 稀疏 / openai / sentence-transformers)→ `knowledge/vector_store.py`(sql_json / chroma / pgvector)
→ `knowledge/retrieval.py`(两级检索+置信度+no-answer)→ `knowledge/reranking.py`。
Provider 抽象:`providers/base.py`(ABC)+ `providers/mock.py` / `openai.py` / `anthropic.py`,工厂在 `providers/__init__.py`。
**国内模型**:`AI_PROVIDER` 可设为 `deepseek` / `qwen`(阿里 DashScope 兼容模式)/ `zhipu`(智谱 GLM)/ `moonshot`(Kimi)——四家均为 OpenAI 兼容端点,复用 `OpenAIProvider` 并注入各自 `base_url`/默认模型;缺少对应 `*_API_KEY` 时自动回退 MockProvider(配置见 `config.py` 与 `.env.example`)。

---

## 9. 测试与质量门(`backend/tests/`,共 267 用例 + 2 skipped)

| 文件 | 覆盖 |
|---|---|
| `test_physics_materials.py` / `test_physics_tmm.py` / `test_physics_beam.py` / `test_physics_coating_tool.py` / `test_physics_nonlinear.py` | 物理内核 vs 解析解与文献值 |
| `test_physics_tmm_oracle.py` | 与独立 `tmm` 库对拍(dev 依赖,缺库自动跳过) |
| `test_physics_adversarial_fixes.py` | 物理内核对抗审查确认缺陷的回归锁 |
| `test_acceptance_hardening.py` | **验收对抗审查**确认缺陷的回归锁:评估器误判(below_spec / AR 当 HR / 显式冲突优先 / 支配维度)、功率拟合折线选段与告警保真、caird 除零与类型容错、导入器空行与数量 0、解析器尾部波长、上传大小门、.txt/.tsv 加载、非 dict 需求 |
| `test_physics_modules.py` | 物理工具经 REST 模块 + Agent 任务 + 聊天路由 |
| `test_power_curve.py` | 功率曲线拟合、跨曲线 Findlay-Clay/Caird、API 往返 |
| `test_inventory.py` | L0 语法解析、导入、SQL 过滤、L1 三态/硬门/前沿、Agent 路径 |
| `test_acl.py` / `test_security_hardening.py` | ACL 与提权/越权回归(角色以 DB 为准、evals 租户隔离、失败回滚) |
| `test_cases/knowledge_agent/generation/agent_memory/...` | 业务 API 全链路 |
| CI:`.github/workflows/ci.yml` | ruff、pytest、SQLite 迁移冒烟、真实 Postgres+pgvector 集成、前端 lint/build |

---

## 10. 可复现演示(`backend/scripts/`)

| 脚本 | 演示内容 |
|---|---|
| `scripts/demo_physics_case.py` | 通用工作流:建 Case → 中文路由 → Agent 任务 → 腔长扫描/相位匹配/镀膜评估 → 引用与审计(内存库+mock LLM,零依赖可跑) |
| `scripts/demo_thg_inventory_case.py --inventory <xlsx>` | **紫外三倍频 vs 真实库存**:解析工作簿 → 库存约束腔设计 → SHG/THG 角 → 库存 BIBO 切角第一性验证(差 0.1°)→ 库存 LBO 逐块偏差量化 → 缺口/实测清单(库存数据仅入内存,不落盘) |

---

## 10.5 前端(`frontend/src/`)

| 文件 | 职责 |
|---|---|
| `App.jsx` | 路由与导航(首页 / Agent / 案例 / 实验室文档 / **元件库**) |
| `pages/CaseDetail.jsx` | 案例详情:概览(结构化参数表)、生成物(分节渲染 + 原始 JSON 折叠)、知识检索、**模块**(分组下拉 + 每模块独立参数框 + 类型化结果)、Agent 任务轨迹、附件;统一错误横幅 |
| `components/ModuleResults.jsx` | **类型化结果渲染**:功率曲线 SVG(坐标刻度 + 实测点 + 阈值标记)、多曲线对比与腔损耗、相位匹配表、镀膜三态色块、腔设计摆位表、元件匹配前沿 |
| `pages/InventoryPage.jsx` | 元件库:xlsx 导入、波长×功能 SQL 级筛选、名称搜索、待复核队列、需求匹配 |
| `pages/AgentWorkspace.jsx` | Agent 对话:路由结果 / 任务 / 引用 pill |
| `api/client.js` | axios 封装 + HTTP 状态码中文提示 |
| `api/inventory.js` | 元件库 API 客户端 |
| `LanguageContext.jsx` / `i18n.js` | 中英双语;`t()` 文案 + `te()` 后端枚举值翻译(状态/置信度/带位/元件名) |

---

## 11. 配置(`backend/app/config.py` + `.env`)

关键开关:`AI_PROVIDER`(mock/openai/anthropic)、`EMBEDDING_PROVIDER`、`RETRIEVAL_BACKEND`
(sql_json/chroma/pgvector)、`RERANKER_PROVIDER`、`REQUIRE_AUTH`/`API_KEY`(生产必开)、
检索阈值组(`retrieval_min_score` 等)。Docker 部署:`docker-compose.yml`(migrations 权威,
`AUTO_CREATE_TABLES=false`)。

---

## 12. 已知边界与下一步

- **物理内核边界(已文档化)**:双轴相位匹配为主平面近似(medium 置信度);TMM 假设无损入射介质;
  含腔内介质时束腰**位置**为光程坐标(尺寸精确);金属镜/GDD 镜/LBO 温度调谐待做。
- **L1 边界**:镀膜三态依赖标称阻带先验,实测曲线导入(`coating_tool` vendor_curve 模式)可逐件升级置信度;
  切角匹配目前在演示脚本中示范(BIBO/LBO),尚未并入 evaluator 的晶体判定维度。
- **L2/L3 方向**:实验室历史先例库(成/败记录)校准 maybe_usable 阈值;LLM 判断层消费 L1 前沿
  (每条结论必须挂在算出的数字或检索到的先例上);整链 propose-verify 耦合搜索。
