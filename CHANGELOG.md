# CHANGELOG

> 状态：生效 ｜ 最后更新：2026-11-01 ｜ 维护：Claude
>
> 每条四段式：做了什么 / 验证证据（命令 + 实际输出）/ 遗留问题 / 规则或评测集变动。
> **验证证据只写真实跑出来的输出，不写"已完成"。**

## v0.2.0 · D2 结案（2026-11-02）

**做了什么**：完成法规结构化入库、BM25 + 向量 + RRF、可追溯术语扩展、domain 过滤及 MCP 六工具；升级 Strict/Relaxed/Partial 评测与 A–E 归因，新增独立 Top50 诊断。定点补词仅来自现有 violation_quote 子串并记录 source_case_id；第28条(二)子块数值加权未改变生产 Top3 结果，如实记录负结果。本轮结案不再修改检索参数。

**验证证据（真实执行）**：`python -m pytest tests/rag -q` → `35 passed in 1.41s`；`python -m scripts.rag_diagnose` → exit 0；`python -m scripts.rag_diagnose --ab` → exit 0。官方口径固定 Top3，默认真实 rewrite/vector 开启；Top50 仅用于诊断，作用域退出即恢复，不泄漏至官方评测。

| 指标 | 值 |
|---|---|
| Strict Recall@3 | 9/15（60%） |
| Relaxed Recall@3 | 12/15（80%） |
| Partial 率 | 3/15 |
| Top1 | 4/15 |
| 条号准确率 | 9/45 |
| 归因 | A=3 / D=3 / **B=0 / C=0 / E=0** |

真实 A/B：RRF k 60→10，Strict 9→9；探索性 Top5 不改变官方 Top3 口径，Strict 9→9；rewrite 开→关，Strict 9→10；lexicon 开→关，Strict 9→5。证据保存在 tests/rag/d2_*.json；基线旧格式与新诊断格式并存，不覆盖为虚构结果。

**遗留问题 / 技术债**：
1. **B/C/E 归因为 0** → 本冻结集诊断支持数据管线健康，当前瓶颈在语义匹配与排序，不是已发现的索引缺失或过滤工程缺陷；这不是对全部工程路径无缺陷的证明。
2. **A=3 是标注口径问题** → 已按法理补 acceptable_codes，Relaxed 12/15；Strict 仍为 9/15，不拿宽松指标冒充达标。
3. **负结果：`rewrite` 开启反而更低（9→10）**（箭头表示关闭改写后的变化），`lexicon` 关闭则掉到 5/15 → 本轮术语扩展有效、当前改写策略有害，**改写需重做**。技术债：改写仅作术语扩展的补充查询，保留原话术强信号，重新设计查询池融合与贡献约束，并以独立样本复核；当前实现已将原话术保留在池内，问题不是代码字面替换原话术。
Strict 与条号准确率未达原目标，D2 按实测结案，不宣称质量指标通过。不继续靠加权硬挤 Top3，那是用指标驱动排序，不是解决语义鸿沟。

**规则或评测集变动**：沿用已冻结 expected_codes 与查询；acceptable_codes 的法理补充已独立提交 b153cd4，不根据返回结果改标签。新增三指标及归因，不改官方 top_k=3；无业务判定规则或表结构变动。test_domain 的 coverage 检验改用注入 fixture，避免生产词表变动导致断言漂移。

## D2续 · 真实入库通过，案例门禁暂停

**改动说明/行为变化**：修复embedding忽略JUDGE_BASE_URL的错误，读取EMBEDDING_MODEL；
当前网关批量25条返回400（明确限制10），故默认10条，仍不超过25上限。
新增带原话来源追溯的八类词表及确定性扩展，多查询统一RRF；检索行为有变化。

**实际验证**：配置七键齐全（未打印值）。build_index成功连续两次，解析164法条块/2案例，
跳过54 procedure；两次真实count均law_articles=164、case_fines=2，独立get_collection读回一致。
完整测试85 passed in 8.30s。三个真实请求demo均bm25+vector+lexicon+rewrite。

**风险/遗留**：阶段C前仅2案例，按门禁暂停，不重写或运行旧评测集。
八类词表只有efficacy_claim 6词、safety_guarantee 1词，其余0词，明确标记不足，
未用文档示例或虚构变体补足。网关改写已成功，但个别检索仍召回农药/种子法条。
需统筹补至少8独立真实案例及足够类别原话，再冻结新评测集和报分类命中表。

**规则/评测变动**：未改法规、规则、表结构；旧查询集保留但作废，不作为本轮指标。

## D2 · 目录收敛与 RAG/MCP 实现（验收未完成）

**做了什么**：D1 合并远端 main（84c7c58）并打 v0.1.0；六目录逐个收敛并
分别提交，每次回归 45 passed（原44条加上轮校验测试），未减少测试。
阶段A按先截正文、再选择编号风格、最后检查连续性返工，五份法规全部通过。
新增 ingest/embedding/retrieve、build_index/evaluate_rag、MCP六工具及隔离测试。

**验证证据**：完整套件 83 passed in 8.46s；verify_law 74/12/10/12/18 条
连续、退出0；MCP selftest六工具注册通过。实际解析164个法条块、跳过54条
procedure、2案例块；平均66.53字，最长292，最短17。
build_index 实际退出1：缺少 JUDGE_API_KEY，两个collection读回均0，未生成替代向量。
冻结查询集SHA256 7ac1b879f10866621d793923be4910b4b81bc259e7b052c6f16ef3e2a01215cb。
纯BM25降级 Recall@3=4/15，返回条号准确率=4/44，Top1=0/15；未达到验收线。

**遗留问题**：本地.env无JUDGE_API_KEY，真实向量入库/幂等验证、LLM改写、
混合检索指标均待配置后重跑；不得声称D2通过，不合并D2到main、不打D2完成标签。
无检测器新增，Detector registry在D3实现；本轮未改判定规则或表结构。
红队结果暂存被gitignore的data/redteam/results.jsonl，待D4确认正式存储契约。
README列出的06–08法规文件当前不存在，本轮只读处理实际五份。

**规则或评测集变动**：未改任何法条/规则/业务表；评测15查询来自仅2案例的
连续原话子串，继承案例原法条标签，是相关查询集而非15个独立罚单；需人工复核。

## D2 · A · 完整性校验受阻（分支 `feat/d2-rag-mcp`）

**做了什么**：新增 `scripts/verify_law.py` 和独立 unittest；按任务指定的
`^第([一二三四五六七八九十百]+)条` 提取条号，排除台账 README；支持
`--allow-gap`，空匹配仍失败，广告法校验最大条号 74。未改任何语料。

**验证证据**：指定 Python 运行 `python -m unittest tests.test_verify_law -v`
先失败（模块不存在），实现后 `Ran 1 test / OK`；
`python -m scripts.verify_law` 返回 1：广告法 1–74 连续，02/03/05 空匹配，
04 仅匹配到文末分块说明“第五条的 3 项”，报告缺 1–4。
诊断显示指南正文实际用“一、”“二、”编号，与指定正则不兼容。

**遗留问题**：按阶段 A 停止条件暂停 B–F。需确认允许将正文范围内的
“中文数字、”也作为条号，并排除文末入库建议，才能重新核验全部五份。
当前失败不等同于已证实语料缺失，禁止根据此结果补写法条。

**规则或评测集变动**：无；未改 rules/audits、判定规则、评测集或语料。

## v0.1.0 · D1 · 骨架与鉴权（2026-11-01，分支 `feat/d1-skeleton-auth-crud`）

### A · 目录骨架与核心配置（commit a9bb651）
**做了什么**：按 CLAUDE.md §3 建分层目录与包 docstring；pydantic-settings 读 `.env`；
`constants.py` 集中分数/8 轴/免责声明；统一返回体与全局异常处理器；`/health`。

**验证证据**：
```
$ python -c "TestClient(app).get('/health') / get('/nope') / options('/health', Origin=localhost:5173)"
200 {"code":200,"msg":"ok","data":{"status":"ok","version":"0.1.0"},"total":null}
404 {"code":404,"msg":"Not Found","data":null,"total":null}
CORS 200 http://localhost:5173
```

### B · 五张业务表与幂等建库（commit 422e891）
**做了什么**：users/clients/scripts/audits/rules 五个 ORM 模型；`scripts/init_db.py`
默认只预览 DDL、`--apply` 才执行；全部 `CREATE TABLE IF NOT EXISTS`；
`audits` 加 `CONSTRAINT ck_audits_score CHECK (score BETWEEN -1 AND 2)`。

**验证证据**：
```
$ python -m scripts.init_db --apply        # 第 1 次
INFO 新建表: clients（索引 0 个） / rules（1） / users（0） / scripts（1） / audits（2）
INFO 建表完成，新建 5 张: ['clients', 'rules', 'users', 'scripts', 'audits']
EXIT 0
$ python -m scripts.init_db --apply        # 第 2 次（幂等）
INFO 跳过已存在的表: clients / rules / users / scripts / audits
INFO 建表完成，新建 0 张: 无（均已存在）
EXIT 0
mysql> SHOW TABLES;      -> audits, clients, rules, scripts, users（5 张）
mysql> SHOW CREATE TABLE audits;
  CONSTRAINT `ck_audits_score` CHECK ((`score` between -(1) and 2))
mysql> START TRANSACTION; ...INSERT INTO audits(script_id, score) VALUES (<id>, 99); ROLLBACK;
ERROR 3819 (HY000) at line 1: Check constraint 'ck_audits_score' is violated.
mysql> SELECT COUNT(*) ...  -> clients 0 / scripts 0 / audits 0（探针已回滚，无残留）
```

### B-docs · 契约回写
**做了什么**：`db_schema.md` 写明 NOT NULL / CHECK / `updated_at ON UPDATE` / 索引名；
`RUNBOOK.md` 启动命令改为 `init_db --apply`；`SKILL.md` 加 S2 与 Hermes 私有技能索引。

**验证证据**：`git diff --stat` 见对应 docs commit。

### C · JWT 注册登录与鉴权依赖（commit 190f9f7）
**做了什么**：`security.py`（bcrypt 哈希 + HS256 JWT）、`deps.py`（`get_current_user`，401 带
`WWW-Authenticate`）、`/api/v1/auth/register|login|me`；登录失败统一提示防枚举。

**验证证据**（uvicorn :8765 实跑，`curl.exe`）：
```
GET  /health                         -> [HTTP 200] {"code":200,"msg":"ok","data":{"status":"ok","version":"0.1.0"},"total":null}
POST /api/v1/auth/register           -> [HTTP 200] {"code":200,...,"data":{"id":4,"username":"curl_demo","role":"operator"}}
POST /api/v1/auth/login (错密码)     -> [HTTP 401] {"code":401,"msg":"用户名或密码错误","data":null,"total":null}
POST /api/v1/auth/login (正确)       -> token len: 176
GET  /api/v1/clients (无 token)      -> [HTTP 401] {"code":401,"msg":"缺少 Authorization: Bearer ***",...}
GET  /api/v1/auth/me (Bearer)        -> [HTTP 200] {"data":{"id":4,"username":"curl_demo","role":"operator","created_at":"2026-11-01T17:01:01"}}
```

### D · 四套 CRUD（commit 137fe05）
**做了什么**：clients/scripts/audits/rules 各 schemas+crud+service+api；分页 `page/page_size`
返回 `{code,msg,data,total}`；scripts/audits 支持 `client_id`；不存在 id -> 404；
外键约束删除 -> 409；script 指向不存在的 client -> 422；rules axis 越界 -> 422；
rules 改内容 -> 新行 version+1、旧行 enabled=0 保留（铁律 7）。

**验证证据**：
```
POST /api/v1/clients                 -> [HTTP 200] {"data":{"name":"curl-demo-clinic","industry":"medical_beauty","plan":"free","id":3,...}}
GET  /api/v1/clients?page=1&page_size=20 -> [HTTP 200] {"code":200,"msg":"ok","data":[{...id:3...}],"total":1}
GET  /api/v1/clients/999999          -> [HTTP 404] {"code":404,"msg":"client 999999 不存在","data":null,"total":null}
```
curl 产生的探针数据已删除：业务库 users/clients/scripts/audits/rules 均为 0 行。

### E · 种子与测试（commit 4f0a875）
**做了什么**：`data/cases/` 2 条真实罚单（case_001 即 db_schema §2.2 契约示例；case_002 取自
市场监管总局 2025-07-09 公布的典型案例，成都成华韩后医美，罚 40.98 万）；`seed_cases.py`
做结构校验；pytest 用独立库 `compliance_guard_test`。

**验证证据**：
```
$ python -m scripts.seed_cases
有效案例: 2 条 / 目标 30 条
  - samr_2025_002 | 2024 | 罚款 613700 元 | 上海市市场监管局 | 功效/安全性断言
  - samr_2025_hou | 2025 | 罚款 409800 元 | 四川省成都市成华区市场监管局 | 功效断言/虚假广告
EXIT 0
$ python -m pytest tests -q
44 passed in 3.28s
EXIT 0
mysql> 业务库计数 -> users 0 / clients 0 / rules 0（测试未污染业务库）
自检：print( 0 处 / 裸 except 0 处 / .query( 0 处 / 已跟踪文件中密钥 0 处 / 函数 >60 行 0 个 / 最大文件 166 行
```

**遗留问题**
- seed_cases 在 D1 只做校验，未写 Chroma（入库属 D2 `build_index.py`）。
- case_001 处罚决定书编号待人工核对；锚点集 2/30。

**规则 / 评测集变动**
- 无（rules 表为空；锚点集尚未入 Chroma）
