# SKILL.md — 技能库（熵管理）

> **状态：草案（仅收录已验证做法，未验证的不许写进来）** ｜ 最后更新：2026-11-01 ｜ 维护：统筹方 + Claude
>
> Harness 组件⑤⑥：**每次踩坑 → 沉淀为技能；过期技能 → 定期清理**。
> 规则：**只有"跑通过一次"的做法才能写成技能**；写"打算这么做"的，一律删。

---

## 使用约定

每条技能固定六段：**场景 / 步骤 / 关键代码 / 陷阱 / 验证方式 / 最后验证日期**。
超过 60 行的技能应拆成独立文件放 `skills/`，本文件只留索引。

---

## 技能索引

| # | 技能 | 状态 | 验证日期 |
|---|---|---|---|
| S1 | FastAPI 统一返回体 + 全局异常 | **已验证**（见 S1/S3/S4） | 2026-11-01 |
| S2 | SQLAlchemy 2.0 建模 + 幂等建表 + CHECK 约束 | **已验证**（见下文 S2） | 2026-11-01 |
| S3 | JWT 鉴权依赖注入 | **已验证** | 2026-11-01 |
| S4 | Pydantic V2 校验与分页参数 | **已验证** | 2026-11-01 |
| S5 | Chroma collection 建库与 metadata 过滤 | TODO（D2） | — |
| S6 | MCP 工具注册与 selftest | TODO（D2） | — |
| S7 | LangChain 工具调用（Tool 绑定） | TODO（D3） | — |
| S8 | 引文子串校验（quote → 原文定位） | TODO（D3） | — |
| S9 | Vue3 + Element Plus 表格/表单页骨架 | TODO（D5） | — |
| S10 | 可选引擎懒加载 + 能力探测由注册表现算 | **已验证**（全文 `skills/doc-parse-engines.md`） | 2026-11-04 |

### Hermes 私有技能索引（技能全文在 Hermes 目录，此处只做可审计登记）

| 技能名 | 适用场景（一行） | Hermes 技能路径 | 登记日期 |
|---|---|---|---|
| `fastapi-spec-driven-build` | 按契约文档（CLAUDE/db_schema/api_spec）分阶段闸门式搭建 FastAPI + SQLAlchemy 2.0 + MySQL 后端 | `~/.hermes/skills/software-development/fastapi-spec-driven-build/SKILL.md` | 2026-11-01 |

> 规则：Hermes 每自动沉淀一个与本项目相关的技能，当轮在此表加一行；技能删除时同步删行。

---

## S0 · 环境坑：Chroma 与 protobuf 冲突（**已验证，2026-11-01**）

**场景**：`import chromadb` 抛 `TypeError: Descriptors cannot be created directly`

**根因**：`opentelemetry-proto` 版本落后于 `protobuf 7.x`

**步骤**：
```bash
python -m pip install -U opentelemetry-proto opentelemetry-api opentelemetry-sdk -i https://pypi.tuna.tsinghua.edu.cn/simple
python -c "import chromadb; print(chromadb.__version__)"   # 期望 1.5.9
```

**陷阱**：不要靠降级 protobuf 解决（会连锁破坏 langchain 生态）；也不要设
`PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python`（可行但慢 10 倍以上）。

**验证方式**：上面前两句都成功 → 技能有效。

---

## S2 · SQLAlchemy 2.0 建模 + 幂等建表 + CHECK 约束（**已验证，2026-11-01**）

**场景**：按 `db_schema.md` 建 MySQL 表，要求可预览、可重复执行、取值域由库强制。

**步骤**：
1. 模型用 `Mapped` / `mapped_column`；有 DEFAULT 的列一律 `nullable=False` + `server_default=text(...)`
2. 取值域写成 `CheckConstraint(..., name="ck_<表>_<列>")` 放进 `__table_args__` 元组（最后一项放 mysql 选项字典）
3. `scripts/init_db.py`：用 `CreateTable(table, if_not_exists=True)` 编译成 MySQL 方言字符串，
   **预览和 `--apply` 共用同一份字符串**；无参只预览，`--apply` 才执行

**关键代码**：
```python
__table_args__ = (
    CheckConstraint(f"score BETWEEN {SCORE_INCOMPLETE} AND {SCORE_COMPLIANT}", name="ck_audits_score"),
    MYSQL_TABLE_ARGS,
)
score = mapped_column(SmallInteger().with_variant(TINYINT(), "mysql"), nullable=False)
ddl = str(CreateTable(table, if_not_exists=True).compile(dialect=mysql.dialect()))
```

**陷阱**：
- MySQL 8 **没有** `CREATE INDEX IF NOT EXISTS`：索引只在"本次新建的表"上执行，已存在的表靠 `inspect().get_table_names()` 反射跳过
- `CreateTable` 不含二级索引，要单独 `CreateIndex` 编译，否则预览与实际执行不一致
- `TINYINT` 要用 MySQL 方言 variant，通用 `SmallInteger` 会生成 SMALLINT
- `updated_at` 要库侧 `ON UPDATE CURRENT_TIMESTAMP`，只写 ORM `onupdate` 绕过 ORM 就失效
- WSL 下调 Windows `python.exe` 输出中文乱码：加 `PYTHONIOENCODING=utf-8 WSLENV=PYTHONIOENCODING`（原生 Windows 终端无此问题）

**验证方式**：`--apply` 连跑两次（第二次"新建 0 张"、退出码 0）；`SHOW CREATE TABLE audits` 含
`ck_audits_score`；插入 `score=99` 报 `ERROR 3819 ... Check constraint 'ck_audits_score' is violated`。

**最后验证日期**：2026-11-01

---

## S1/S3/S4 · 统一返回体、JWT、分页校验（**已验证，2026-11-01**）
**场景**：D1 鉴权 + 四套 CRUD。
**做法**：
1. 鉴权用 `bcrypt` + `PyJWT` 直连，**不用 passlib**（1.7.4 与 bcrypt 4.x 报 `__about__` 警告且已停维）。
2. `get_current_user` 用 `HTTPBearer(auto_error=False)`，自己抛 401 并带 `WWW-Authenticate: Bearer`；默认 auto_error 会给 403，与契约不符。
3. 登录失败（用户不存在 / 密码错 / 已停用）统一一句"用户名或密码错误"，防账号枚举。
4. 分页 `page>=1, 1<=page_size<=100` 用 `Annotated[int, Query(ge=, le=)]`，越界由全局 `RequestValidationError` 处理器转 400。
**坑**：
- Pydantic 字段若声明成 `Literal[8 轴]`，越界被请求校验拦成 **400**，但 `api_spec §3` 要求 axis 越界 **422**（业务校验）。做法：schema 里 axis 用 `str`，在 service 层对照 `constants.AXES` 抛 422。
- 外键 RESTRICT 删除父记录时 MySQL 抛 `IntegrityError 1451`，service 层捕获转 **409**，否则落到 500。
- 测试库隔离：conftest 在 import `backend.*` 之后替换 `db_session.engine/SessionLocal` 指向 `<库名>_test`；`get_db` 内部按名取 `SessionLocal`，因此替换生效。跑完核对业务库各表 0 行。
- WSL 里用 `cmd &` 起 Windows python 的 uvicorn 会随 shell 退出被杀，必须用 Hermes `terminal(background=true)` 起服务，再 `curl.exe` 打 `127.0.0.1`。
**验证**：`pytest tests -q` -> `44 passed`；curl 实测见 CHANGELOG v0.1.0 C/D/E。

## S5 · Chroma/DashScope 适配与 RRF 降级（部分验证）

**场景**：仅用远程 text-embedding-v3，禁止隐式下载默认模型。
**步骤**：显式传入自定义 embedding_function；input 参数名遵循 Chroma 协议；
批量25条并校验1024维；稳定ID upsert。Retriever组合VectorIndex协议与BM25，
RRF用1/(60+rank)，不直接相加异量纲分数。
**关键代码**：见 backend/rag/embedding.py 与 retrieve.py。
**陷阱**：空collection必须标 vector_unavailable，不可当作正常向量空召回；
密钥缺失时保留BM25且route标degraded。重排加分不能用于制造低分匹配。
**验证方式**：分批51条得到25/25/1、坏向量报错、RRF名次融合、断网BM25测试通过；
实际collection创建通过，但本地缺密钥，真实DashScope入库与混合召回尚未验证。
**最后验证日期**：2026-11-02（只确认上述离线行为，非端到端验收）。

## S6 · MCP 六工具离线自检（已验证）

**场景**：FastMCP stdio协议工具注册。
**步骤**：用mcp.tool装饰六个独立工具，selftest调用list_tools读取真实注册表。
**关键代码**：backend/mcp_server/server.py；RAG工具复用retrieve.search。
**陷阱**：selftest不调用数据库或LLM；audit_recheck返回pending_d3，不冒充审查完成。
**验证方式**：--selftest输出六工具和inputSchema；隔离测试24条通过。
**最后验证日期**：2026-11-02。

## S5补充 · 已验证的远程接入

**场景**：兼容网关embedding真实入库。
**步骤**：读取JUDGE_BASE_URL，配置EMBEDDING_MODEL；本次网关实际只允许10条批次，
不要把上游25条上限当成所有兼容网关都支持的值。
**关键代码**：embedding.py默认批次10，可由EMBEDDING_BATCH_SIZE指定且不得超过25。
**陷阱**：只打印HTTP状态可能掩盖批次限制；诊断响应必须脱敏。词表必须保留来源案例映射，
语料缺少某类时保留空表及不足状态，不能凭空补词。
**验证方式**：两次真实upsert后独立count均164/2；断网词表+BM25测试通过。
**最后验证日期**：2026-11-02。

## 变更记录
| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-11-01 | 建立索引与 S0（Chroma protobuf 坑） | 启动前环境修复 |
| 2026-11-01 | 加 S2（幂等建表 + CHECK）与 Hermes 私有技能索引 | D1 建库验证通过；技能可审计 |
| 2026-11-01 | S1/S3/S4 验证并记录 4 个坑（422 vs 400、1451->409、测试库隔离、WSL 后台进程） | D1 C/D/E 完成 |
