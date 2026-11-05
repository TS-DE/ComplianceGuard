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
| Agent 框架 | **LangChain** 只作模型适配层（`backend/model/langchain_model.py`，`LLM_BACKEND=langchain` 可切换）；**LangGraph 未接入代码**——判定编排是显式实现，N1→N10 顺序写死在 `ComplianceAuditAgent.review`，不为了"用了编排框架"去重写判定链路 |
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
│   ├── api/v1/           # 路由层：auth / resources(四套 CRUD) / ingest(素材摄取与档案) / ai
│   ├── services/         # 业务编排：audit / rewrite / redteam / report
│   ├── agents/           # 5 个 Agent + base.py + mcp_client.py
│   ├── tools/            # rag_tool / db_tool / ingest_tool（MCP 工具的本地实现）
│   ├── parse/            # 素材摄取：base 抽象+注册表 / split 切分与绝对锚点 / parsers 子包(documents,media)
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

### 3.1 目录规模上限（硬约束）

> **一个目录内的 `.py` 文件数 ≤ 3**（`__init__.py` 不计）。超过 3 个必须二选一：
> **① 合并**——同类小文件合成一个（如 5 张表的 ORM 合成 `db/models.py`）；
> **② 建子包**——按业务域分（如 `agents/compliance/`、`agents/redteam/`）。

**它和"单文件 ≤300 行"必然打架，冲突时按此优先级**：
先按职责拆（宁可多一个文件）→ 再按行数拆（`xxx_base.py`/`xxx_impl.py`）→
最后才允许放宽行数，**且必须在 CHANGELOG 写理由**。
**永远不允许靠"堆文件"绕过 300 行，也不允许靠"塞一个文件"绕过 3 文件上限。**

**目标结构（每层 ≤3 文件）**：
```
backend/
├── main.py
├── core/        config.py · security.py · errors.py      （deps 并入 security）
├── db/          session.py · models.py                   （6 张表合一个文件）
├── schemas/     common.py · auth.py · business.py        （4 套资源 schema 合一）
├── crud/        base.py · special.py                     （泛型 Repository + 特例）
├── api/v1/      auth.py · resources.py · ai.py + ingest/ 子包 （4 套 CRUD 用 router 工厂）
├── services/    compliance.py · redteam.py · report.py
├── agents/      base.py · compliance.py · redteam.py     （A1+A2 / A3+A4+A5）
├── rag/         ingest.py · embedding.py · retrieve.py
└── mcp_server/  server.py
```

> **不是"文件越少越好"**：合并的必须是**同类**（5 张表、4 套 CRUD），不是把不相干的塞一起。
> 判断标准是"**它们的变化原因是否相同**"（SRP，见 §6.1）。

## 4. Harness 六大组件 → 本项目落点（必须可指认）

| # | 组件 | 本项目落点 | 证据文件 |
|---|---|---|---|
| ① | 上下文工程 | `.hermes.md` 做入口，按 D1–D7 阶段 **渐进披露**：D1 只读 `db_schema.md`+`api_spec.md`(auth)，D3 才读 agent 部分 | `.hermes.md` |
| ② | Agent 专业化 | `AGENTS.md` 拆 5 个业务 Agent + **6 个开发子 Agent**（DB / Backend / Agent / Frontend / Test / Doc）。开发子 Agent 是**文档约定的分工角色**（规定"谁能改哪个目录"），不是程序、不会自己跑；业务 Agent 才是产品里真跑流程的类 | `AGENTS.md` |
| ③ | 持久化记忆 | `~/.hermes/MEMORY.md`（进度、遗留 BUG、接口清单）+ `USER.md`（偏好：中文注释、Pydantic V2、不许裸 except） | 见 §9 |
| ④ | 架构约束 | ①MySQL 变更必须先出 SQL 预览、禁 DROP/TRUNCATE ②JWT 鉴权不可绕过 ③LLM 失败降级为纯规则 ④每次提交可回滚 ⑤密钥只走 `.env` | `RUNBOOK.md` |
| ⑤ | 反馈循环 | 红队漏杀样本 → 生成规则候选 → **人工审核后**才入 `rules` 表并 bump version；失败轨迹记入 `CHANGELOG` | `EVAL.md` |
| ⑥ | 熵管理 | `SKILL.md` 只留**已验证可用**的技能；文档审校只做三件事——删过时、并重复、标过时；漂移靠 `python -m scripts.doc_lint` 机械检查（路径存在性、数量与代码事实、技术栈是否真有 import、每目录文件数），**红灯不许收工** | `scripts/doc_lint.py` |

### 4.1 术语三分（答辩防绕晕）

项目里"Agent"这个词指三类东西，**数量和性质都不同**，混着说会被问倒：

| 名称 | 数量 | 是什么 | 会不会真跑 |
|---|---|---|---|
| 业务智能体 A1–A5 | 5 | 产品里真跑流程的 Python 类（`backend/agents/`：ComplianceAudit / Rewrite / RedTeam / Judge / AuditReport） | **会**，请求进来就跑 |
| 开发子 Agent | 6 | `AGENTS.md` 里的**分工角色**：规定每个角色只能改哪个目录、交付前要自己跑通哪部分测试 | **不会**，它是规矩不是程序 |
| MCP 工具 / 规则轴 / 检测器 | 8 / 11 / 3 | 被上面那些类调用的**零件**：工具走 MCP 契约，轴是 `rules` 表的分类，检测器是 `DETECTORS` 注册表 | **不会**，它们不是 Agent |

> 口径来源：工具数取自 `backend/mcp_server/server.py` 的 `@mcp.tool`，轴数取自
> `data/seeds/rules.json` 的去重 axis，检测器数取自 `backend/agents/base.py` 的 `DETECTORS` 键，
> 业务智能体数取自 `backend/agents/*.py` 的 `class *Agent`。这四组数字由 doc_lint 与代码对账，
> 文档里写错会直接报红灯。

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

### 6.1 面向对象七大原则（硬约束，每个新模块都要能对应上）

| # | 原则 | 本项目落点（必须可指认） |
|---|---|---|
| 1 | **SRP 单一职责** | `api` 只做参数校验与返回；`services` 只做编排；`crud` 只碰数据库；`agents` 只做判定/生成。**一个类只有一个"变化原因"** |
| 2 | **OCP 开闭** | 新增一条规则**不改代码**（写 `rules` 表）；新增一种检测手段**不改判定器**（往 registry 注册一个 `Detector` 子类） |
| 3 | **LSP 里氏替换** | `ChatModel` 抽象可换 urllib / langchain；`Detector` 抽象可换 keyword / regex / llm_judge——**换实现不改变调用方语义** |
| 4 | **ISP 接口隔离** | 工具是 6 个独立 MCP 工具，**不做** `ToolService` 这种大而全接口；Agent 只依赖自己用到的那几个 |
| 5 | **DIP 依赖倒置** | `services` / `agents` 依赖 `ChatModel`、`Retriever`、`Repository` **抽象**，**禁止直接 import `chromadb` / `openai` / SQLAlchemy Session 到业务层** |
| 6 | **LKP 迪米特（最少知道）** | `api` 不许链式穿透 ORM 关系（`client.scripts[0].audits`）；要数据就调 service |
| 7 | **CRP 合成复用** | Agent **组合** `Retriever` + `RulesRepo`，**不要**继承一个"万能 BaseAgent"（继承层级 >2 层即视为违反） |

**具体的落地接口（D2/D3 必须照此实现）**：

```python
# backend/agents/base.py —— OCP + LSP + DIP 的落点（检测器与 DETECTORS 注册表同处一文件）
class Detector(ABC):
    @abstractmethod
    def detect(self, text: str, rule: Rule) -> list[Hit]: ...

class KeywordDetector(Detector): ...   # 对应 rules.detector = 'keyword'
class RegexDetector(Detector): ...     # 'regex'
class LLMJudgeDetector(Detector): ...  # 'llm_judge'

DETECTORS: dict[str, Detector] = {...}  # 注册表：新增手段 = 加一行，不改判定器
```

> **为什么写进硬约束**：`rules.detector` 这一列如果不用多态实现，就会退化成一串 `if detector == 'regex': ... elif ...`——
> 那就是典型违反 OCP。**有注册表，才叫"可扩展"；没有注册表，只是"多了个字段"。**

### 6.2 基础规范

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
7. **阶段验收通过后必须合并 `main` 并打 tag**（`git checkout main && git merge --no-ff <分支> && git tag -a vX.Y.Z`）。
   **理由**：`main` 是唯一可展示的状态。长期只在 feature 分支上开发，会导致 GitHub 首页看不到任何代码
   （2026-11-02 实际踩过：main 停在初始化，代码全在分支上，老师/作者都以为"没上传"）。
8. **每次汇报必须贴 `git log --oneline -n 5 origin/main`**，证明代码确实到了远端主分支。
9. 汇报必须含「**目录规模自检**」：列出 `backend/` 下每个目录的 `.py` 文件数，
   超过 3 个的要说明合并/分子包方案。

10. **改 `db_schema.md` 必须同轮产出迁移**（硬规则，2026-11-02 踩坑后加）。
    凡是修改表结构文档（加列/改类型/加索引），**同一轮必须交付**：
    ① 幂等迁移脚本（用 `inspect(engine).get_columns()` 做列存在性守卫，可重复执行）；
    ② 迁移前后各一份 `SHOW CREATE TABLE xxx` 证据；
    ③ CHANGELOG 记录"文档变更 → 迁移 → 验证"三段。
    **理由**：D1 建表后我在 `db_schema.md` 加了 `detector`/`exemptions` 两列却没给迁移，
    导致文档说有两列、库里没有——**文档变成"看起来对、跑起来错"的假契约**，
    D3 一开始就被这个缺列卡住。

11. **单线程顺序执行，禁止委派子 Agent**（成本纪律，2026-11-02 加）。
    除非用户/统筹方**明确授权**并行，否则：
    - **不许** `delegate_task`、不许开 sub-agent、不许并行子任务；
    - 若判断"必须并行才能完成"，**先停下来说明理由**，等确认后再动。
    **理由**：每个子 Agent 都有自己的上下文窗口，会**重复读取** `CLAUDE.md`、必读文档与仓库状态，
    N 个子 Agent ≈ N 倍输入 token；主 Agent 还要汇总它们的输出再消耗一遍。
    实测代价：一次任务因多次委派，token 成本高出数倍。
    另有一次并发改动把路由入口改成了另一套结构（`backend/api/v1/router/__init__.py`），
    **并发改同一工作区会产生结构漂移**。
    （该漂移已于 2026-11-04 收掉：唯一聚合入口回到 `backend/api/v1/__init__.py`，`router/` 子包删除。
    留两个聚合入口的代价是"加一个 router 只注册了一半"，报错还看不出来在哪半。）
    **允许委派的唯一情形**：任务彼此独立、互不共享文件，且已获授权。

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

**已确认可用**（`pip show` 实测，均在 `E:\Anaconda_download\envs\py312_env`）：fastapi 0.141.1 /
sqlalchemy 2.0.52 / PyMySQL 1.2.0 / chromadb 1.5.9 / langchain-core 1.7.0 / langchain-openai 1.7.2 /
pydantic 2.13.5 / uvicorn 0.52.4。env 里另有 langchain 1.4.7 等包；
langgraph 1.2.16 **已安装、未接入代码**（判定编排是显式实现，见 §2 技术栈行）。

**禁止**：新建虚拟环境、用系统全局 Python、把依赖装到 C 盘（C 盘空间紧张）。

**user-site 污染（2026-11-04 查明，跑项目必须带 `PYTHONNOUSERSITE=1`）**：
`C:\Users\<user>\AppData\Roaming\Python\Python312\site-packages` 也在 sys.path 里，
且**优先于** E 盘 env 命中。SQLAlchemy 与 PyMySQL 曾经只存在于这个目录——
`requirements.txt` 钉了版本、`pip` 也说 "already satisfied"，但 env 里其实一个文件都没有。
现已用 `--ignore-installed` 真正装入 E 盘 env，并用
`set PYTHONNOUSERSITE=1&& python -m pytest tests -q` → 319 passed 证明该 env 可独立跑通。

两条由此而来的硬规矩：
1. 装包后必须验加载来源，别信 pip 的 satisfied：
   `python -c "import sqlalchemy; print(sqlalchemy.__file__)"` 应指向 E 盘；
2. 启动后端/跑测试统一加 `PYTHONNOUSERSITE=1`，否则 C 盘副本会静默覆盖 env 里的版本，
   换一台机器就复现不出来。

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
