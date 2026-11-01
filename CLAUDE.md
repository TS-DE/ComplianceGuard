# CLAUDE.md — ComplianceGuard 项目全局规则

> **本文件是给 AI 编码助手（Hermes + Claude）的唯一规范来源**。与其他文档冲突时以本文件为准。
> 配套入口：`.hermes.md`（上下文总控）→ `AGENTS.md`（子 Agent 分工）→ `SKILL.md`（技能库）。
> ⚠️ **不在本项目范围内**：`D:\A Role Consistency Assistance Engine for Creators` 已废弃，**禁止读写**。

---

## 1. 项目是什么

**ComplianceGuard**：面向**强监管行业营销话术**的合规审查与红队压测中台。
首个切片：医疗美容 / 口腔（受《广告法》《医疗广告管理办法》约束）。

用户（机构运营）录入或提交一段话术 → 系统两层判定（确定性词库 + LLM 语义轴）→
输出**命中的法条 + 原文引文 + 分数 + 改写建议** → 落库出审计报告；
另有「红队压测」：一个 AI 扮销售试探边界，一个 AI 扮监管抓它，跑完输出**漏杀清单**。

**三问答案（对外表述固定口径）**：
- 行业：强监管营销话术（首个切片医美/口腔）
- 客户：医美连锁机构（全国 5,649 家，头部 10 家仅占 25.17%）+ MCN/代运营
- 痛点：现有工具只能查"违禁词"，查不出"**无违禁词却构成违规**"的组合断言
  （实证：某口腔机构因"**保证**做完能往上走 1—3 个色度""非常的**安全**、非常**高效**"被罚 **61.37 万元**）

**非目标（明确不做）**：
- ❌ 不做通用内容审核（涉政/涉黄/暴恐）——大厂地盘
- ❌ 不出具法律意见，不替代《医疗广告审查证明》的行政前置审查
- ❌ 不做多租户 SaaS、不做计费系统、不做移动端

## 2. 技术栈（真实情况）

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + Pydantic V2 + Uvicorn（Python 3.12） |
| ORM / 数据库 | SQLAlchemy 2.0 + PyMySQL + **MySQL 8.0** |
| 向量库 | **Chroma**（本地持久化，目录 `data/chroma`） |
| Agent 框架 | **LangChain**（工具调用/Chain）+ **LangGraph**（多 Agent 编排） |
| 工具协议 | **MCP**（FastMCP，stdio） |
| 前端 | Vue3 + Vite + TypeScript + Element Plus |
| 知识图谱 | Neo4j（**可选**，默认不启用；仅当需要实体关系时才接） |
| 版本管理 | git |

## 3. 目录结构（硬约束）

```
D:\ComplianceGuard\
├── .hermes.md            # ① 上下文工程：顶层总控 + @引用清单（渐进式披露）
├── CLAUDE.md             # 本文件：模型基础指令（唯一规范来源）
├── AGENTS.md             # ② Agent 专业化：子 Agent 角色与分工
├── SKILL.md              # ⑤⑥ 技能库：可审计、可清理、可复用
├── HARNESS.md            # Harness 六大组件 → 本项目落地矩阵
├── requirements.md       # @引用：业务需求与验收标准
├── db_schema.md          # @引用：MySQL 表 + Chroma collection
├── api_spec.md           # @引用：REST 接口 + MCP 工具契约
├── EVAL.md               # 评测：锚点集、漏杀/误杀口径、规则版本纪律
├── RUNBOOK.md            # 启动 / 回滚 / 故障排查
├── CHANGELOG.md          # 每日四段式
├── README.md
├── .env.example / .gitignore / requirements.txt
├── backend/
│   ├── main.py           # FastAPI 入口（挂路由、中间件、异常处理）
│   ├── core/             # config / security(JWT) / deps / logging / errors
│   ├── db/               # session / base / init
│   ├── models/           # SQLAlchemy ORM（user/client/script/audit/rule）
│   ├── schemas/          # Pydantic V2 请求响应模型
│   ├── crud/             # 纯数据库操作，不含业务判断
│   ├── api/v1/           # 路由层：auth/clients/scripts/audits/rules/redteam/reports
│   ├── services/         # 业务编排：audit / rewrite / redteam / report
│   ├── agents/           # 5 个 Agent + base.py + mcp_client.py
│   ├── tools/            # rag_tool / db_tool（MCP 工具的本地实现）
│   ├── mcp_server/       # MCP 服务端（stdio）
│   └── rag/              # ingest / store / retriever（Chroma）
├── frontend/             # Vue3 + Vite + TS + Element Plus
├── data/
│   ├── law/              # 法条原文（markdown，入库 Chroma）
│   ├── cases/            # 官方罚单案例（json，锚点集）
│   └── chroma/           # 向量库持久化（gitignore）
├── scripts/              # init_db / seed_cases / build_index
├── tests/                # pytest，与 backend 同构
└── _agent_docs/          # 统筹方（DeepSeek 侧）私有材料，**gitignore，不参与开发**
```

**结构规则**：
1. 每个 Python 包必须有 `__init__.py`，一行 docstring 写明职责。
2. 父目录不得出现裸文件（根目录的 md / config 除外）。
3. 单文件 ≤ 300 行、单函数 ≤ 60 行、单类 ≤ 250 行；超了先拆。
4. 常量集中：`backend/core/constants.py`，业务文件禁裸数字。
5. 依赖单向：`api → services → agents/tools → crud → models → core`。
   **禁止** api 直接调 crud 跳过 service（除纯查询）、禁止 crud 反向 import services。

## 4. Harness 六大组件 → 本项目落点（必须可指认）

| # | 组件 | 本项目落点 | 证据文件 |
|---|---|---|---|
| ① | 上下文工程 | `.hermes.md` 做入口，按 D1–D7 阶段 **渐进披露**：D1 只读 `db_schema.md`+`api_spec.md`(auth)，D3 才读 agent 部分 | `.hermes.md` |
| ② | Agent 专业化 | `AGENTS.md` 拆 5 个业务 Agent + 4 个开发子 Agent（后端/前端/DB/测试），用 `delegate_task` 分工 | `AGENTS.md` |
| ③ | 持久化记忆 | `~/.hermes/MEMORY.md`（进度、遗留 BUG、接口清单）+ `USER.md`（偏好：中文注释、Pydantic V2、不许裸 except） | 见 §9 |
| ④ | 架构约束 | ①MySQL 变更必须先出 SQL 预览、禁 DROP/TRUNCATE ②JWT 鉴权不可绕过 ③LLM 失败降级为纯规则 ④每次提交可回滚 ⑤密钥只走 `.env` | `RUNBOOK.md` |
| ⑤ | 反馈循环 | 红队漏杀样本 → 生成规则候选 → **人工审核后**才入 `rules` 表并 bump version；失败轨迹记入 `CHANGELOG` | `EVAL.md` |
| ⑥ | 熵管理 | `SKILL.md` 只留**已验证可用**的技能；每月清理过期技能；文档单一真相 | `SKILL.md` |

## 5. 项目铁律（违反即 Bug，优先级高于任何"优化建议"）

1. **锚点集不来自 AI。** 评测基准必须是**市场监管总局公开罚单原文**（含违规原话+官方定性+罚款额）。
   禁止用模型生成"标准答案"。见 `EVAL.md`。
2. **分数是算出来的，不是模型给的。** 模型只举证（命中哪条规则 + 原文引文 + 法条号），
   聚合规则写在代码里：任一 hard → 0；soft ≥ 2 → 0；soft = 1 → 1；否则 2。
3. **每条命中必须双引文**：①用户话术的**逐字片段**（子串校验，编造即作废）
   ②法条依据（必须来自本次 RAG 检索结果，**不得凭记忆写条号**）。
4. **引不出法条 → 该条命中作废。** 宁漏不造（可解释优先于召回）。
5. **判定未完成 ≠ 通过。** 任一轴调用失败 → `score = -1` + `incomplete = True`，标为"待人工复核"，
   禁止在报告里计入"合规"。
6. **RAG 只提供证据，不作为放行闸门。** 检索不到相似罚单时，语义轴仍要跑，
   但结论标注"无历史案例支撑，置信度低"；**禁止"搜不到就默认放行"**。
7. **规则版本化**：改 `rules` 必须 `version + 1` 并存旧版；同一次提交同时改规则与评测集，
   必须在 CHANGELOG 说明"这是回归集调整还是新留出集"。
8. **红队边界**：只生成广告法域的擦边话术；**不生成**涉政/涉黄/涉暴内容；样本仅存内部库，不外流。
9. **免责声明**：凡是面向终端用户的接口/页面/导出报告，必须带"不构成法律意见"声明。
10. **`_agent_docs/` 不入库**（已在 `.gitignore`）。

## 6. 编码规范

- 注释中文，写清**为什么**；函数 docstring 含入参、返回、异常场景。
- 命名：文件/函数 `snake_case`；类 `PascalCase`；常量 `UPPER_SNAKE`。
- Pydantic V2 语法（`model_config`、`field_validator`），**禁止 V1 写法**。
- SQLAlchemy 2.0 语法（`Mapped` / `mapped_column` / `select()`），**禁止 legacy Query**。
- 所有接口统一返回 `{code, msg, data, total?}`；异常走全局异常处理器。
- 禁止裸 `except`；禁止 `print` 调试（用 `logging`）；禁止硬编码密钥/DSN。
- **Windows 终端是 GBK：不要往 stdout 打 emoji**（会抛 `UnicodeEncodeError`）。

## 7. 与 AI 协作规则

1. 用户/统筹方提需求，**先输出改动文件清单**（路径 + 要点 + 是否新增依赖），确认后再写代码。
2. 改现有文件标注「位置 + 原因」，不要全量覆盖。
3. 每完成一个可验证单元就跑测试/自检，**贴实际输出**，不许只说"已通过"。
4. 跑多命令时**逐个检查退出码**，不要用 `cmd1; cmd2 | Out-Null`（会掩盖前面失败）。
5. 每个开发日结束：更新 `CHANGELOG.md`（四段式）+ git 提交（小步、语义化 commit message）。
6. 遇到需求歧义**先问**，不要自行扩大范围。

## 8. 禁止行为

1. 不擅自换技术栈（不引入 Streamlit、Django、Milvus、Vue2、Vite 以外的构建工具）。
2. 不重构已通过测试的模块；不删除校验/异常捕获/降级逻辑。
3. 不直接执行破坏性 SQL（DROP/TRUNCATE/ALTER 删列）——**必须先给 SQL 预览等确认**。
4. 不输出明文密钥、`.env` 内容、数据库密码（README 与文档里用占位符）。
5. 不在同一轮里既做新功能又做大范围重构。
6. 不往 `D:\A Role Consistency Assistance Engine for Creators` 写任何文件。
7. 不修改 `_agent_docs/` 下任何文件（那是统筹方目录）。

## 9. 环境

| 项 | 值 |
|---|---|
| Python | `E:\Anaconda_download\envs\py312_env\python.exe`（PATH 里的 `python` 就是它，3.12） |
| MySQL | `mysql+pymysql://root:123456@localhost:3306/compliance_guard`（服务名 `MySQL82`，已运行；库不存在则自建） |
| 向量库 | Chroma，持久化目录 `D:\ComplianceGuard\data\chroma` |
| Neo4j | **默认不启用**；确需知识图谱时再引入（`neo4j://localhost:7687`） |
| 前端 Node | 需 Node 18+；`frontend/` 独立 `npm install` |
| 装包 | `E:\Anaconda_download\envs\py312_env\python.exe -m pip install <包> -i https://pypi.tuna.tsinghua.edu.cn/simple` |
| conda（可选） | 先 `setx CONDA_PKGS_DIRS D:\conda-pkgs`，再 `conda install -p <env> -c conda-forge <包> -y` |
| Hermes 记忆 | `~/.hermes/MEMORY.md`、`~/.hermes/USER.md` |

**已确认可用**：fastapi 0.141.1 / sqlalchemy 2.0.52 / PyMySQL 1.2.0 / chromadb 1.5.9 /
langchain 1.4.7 / langgraph 1.2.16 / pydantic 2.13.5 / uvicorn 0.52.4

**禁止**：新建虚拟环境、用系统全局 Python、把依赖装到 C 盘（C 盘空间紧张）。

## 10. 常用命令

```bash
# 后端
python -m uvicorn backend.main:app --reload --port 8000
# 建库建表 + 种子数据
python -m scripts.init_db
python -m scripts.seed_cases
# 构建向量库
python -m scripts.build_index
# MCP 自检（不联网、不花钱）
python -m backend.mcp_server.server --selftest
# 测试
python -m pytest tests -q
# 前端
cd frontend && npm run dev
```

## 11. 输出格式要求

每次代码回复固定四段：**改动说明（文件清单）→ 文件路径 + 完整代码 → 运行/验证命令（含预期输出）→ 风险与待确认项**。
