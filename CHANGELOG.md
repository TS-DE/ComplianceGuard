# CHANGELOG

> 状态：生效 ｜ 最后更新：2026-11-01 ｜ 维护：Claude
>
> 每条四段式：做了什么 / 验证证据（命令 + 实际输出）/ 遗留问题 / 规则或评测集变动。
> **验证证据只写真实跑出来的输出，不写"已完成"。**

## D3 · 阶段F计价与收尾接线

**改动**：audits.cost 唯一授权迁移至可空，默认预览、--apply执行并可重复跳过；Decimal六位计价，配置优先作者填入MODEL_PRICES，缺价返回None并原样持久化NULL。组合根只读Chroma实际文档名；统一字符起点映射；总耗时在save后计量并回填数据库。

**验证**：迁移前cost decimal(10,6) NOT NULL DEFAULT '0.000000'，迁移后decimal(10,6) DEFAULT NULL；生产审计行数4→4；再次apply打印跳过。NULL持久化旧代码实测误存0后修复。成本/迁移/接线13 passed；全量201 passed in 10.52s（随后新增落库耗时测试单独通过）。

**风险**：价格为作者提供的标准价估算，非供应商账单。费用仅涵盖A1模型响应，不涵盖RAG内部rewrite/embedding；唯一真实验收audit_id=6：score=0、incomplete=false、cost=0.031221、latency_ms=114625；引文及本轴条级法条验证通过，但before_after/inducement仍语义误命中，延迟超90秒。验收失败后停止，未改代码重跑；完整JSON/证据/归因见data/d3_fixed_acceptance_report.md。索引正文仍带code前缀，仅返回边界剥离，本轮未重建。

**规则/评测**：未改规则数据、法规正文、冻结检索评测。除cost可空外未改表结构。

## D3 · 召回前置契约更正与正文去重

**改动**：通用“利用患者名义形象作证明”查询接受合法法源集合（医疗广告管理办法第7条、医疗美容广告执法指南第5条）任一命中；独立使用“卫生技术人员”验证第七条区分度。检索输出text移除合成的code前缀，保留独立code、完整parent_text，索引及归档不改。

**验证**：去前缀测试旧代码RED（text仍以code开头），修复后全量176 passed in 10.92s。纯离线BM25/恒等rewrite：通用查询命中医美指南第5条；区分查询Top3为认定指南第7条、管理办法第7条、医美指南第8条，第七条正文含“卫生技术人员”。无付费调用。

**遗留**：法条规范化、引文回填、跨轴校验及审查并发仍待实施；此次未执行真实审查。

**规则/评测**：按用户明确授权调整前置召回断言，不更改冻结罚单评测集、业务规则或排序算法。

## D3 · 空规则 fail-closed 收尾修复

**改动**：空规则或全禁用规则显式返回 reason=no_rules_loaded、incomplete=true、score=-1；审计仓储对 incomplete 强制保存 score=-1，避免上游误传2。全部 detector 抛错的既有 fail-closed 行为新增回归覆盖。

**验证**：空规则测试先因缺少 reason 两次失败；仓储反例先实际写出 score=2 导致测试失败，修复后全量 tests 为 174 passed in 9.97s。前置生产只读检查：rules=11/enabled=11，两列存在；law_articles=164、case_fines=11。

**遗留 / 单次真实验收结果**：修复提交3e6a85a后，仅执行指定case_002原话一次A1（script_id=3/client_id=4），未执行A2、未重跑。audit_id=5，score=0、hit_count=2、incomplete=false、latency_ms=352785、prompt_tokens=8386、completion_tokens=10856。验收不通过：6条命中中4条quote因NFKC标点归一未恢复原文导致find=-1，original_quote映射均可定位，这是对外quote契约bug；法条子集校验通过。未配置单价使cost=0，不代表免费。另见before_after跨轴误命中。未当场改代码或重跑；完整原始JSON及只读落库证据保存在data/d3_acceptance_once.json、data/d3_acceptance_report.md。

**规则/评测**：未改规则与评测标签；未改表结构。

## D3 · 规则迁移与审查/改写智能体（2026-11-02）

**改动说明 / 行为变化**：授权补齐 rules.detector 与 exemptions（唯一表结构例外），灌入 JSON 的11条规则；Detector 注册表、A1 N1–N9、A2 逐稿二次审查及 MCP audit_recheck 去桩已接入。增加 JWT 审查/改写 API、原文位置映射、双引文作废轨迹及豁免痕迹。为保持目录≤3，config.py 与 router.py 迁为同名包入口，旧 import 路径不变；未改 D2 检索或法规。无新增依赖。

**实际验证**：迁移前 /tmp/rules_before.txt 共11行 JSON证据，rules_count=0，无 detector/exemptions；迁移后真实SHOW CREATE含四值ENUM及JSON，其它表结构签名不变。种子count=11，regex=3、llm_judge=8，SQL非NULL豁免=1、absolute_terms JSON长度9；重跑迁移“两列已存在，跳过”，重跑种子 inserted=0/skipped=11/total=11。pytest tests -q：170 passed in 10.17s。case_002真实模型与向量审查audit_id=4，score=0、两轴有效、同句hit_count=1、incomplete=false；真实改写复审通过，MCP复核score=2。完整返回及落库字段见 tests/agents/d3_live.json；三种注入反例见 d3_counterexamples.json。模型返回子项条号导致严格校验作废，修正提示要求逐字复制检索code，未放松校验。一次网络轴失败真实记score=-1，保留数据库记录，未冒充合规。

**风险 / 遗留**：真实端到端审查耗时220850ms；模型仍有网络波动，适配器有限重试，不完整一律-1。价格未配置，cost=0为零单价估算，不是实际免费或账单金额；失败重试可能产生无法从失败响应计量的费用。经营理念豁免目前仅保守覆盖明确愿景且无疗效保证的情形，其余豁免需进一步语义证据，不声称全覆盖。AGENTS.md流程更新被保护文件写入授权超时阻止，未绕过。范围豁免常量不入表。数据库验收保留标记为D3验收的机构/话术/审查记录（包含失败尝试），无破坏性清理。

**规则 / 评测变动**：既有11条种子原样读取，未改规则内容或冻结评测标签；新增检测器、引文、法条、豁免、重审及持久化测试。分数只由代码算，命中少于原稿可按任务契约通过但不等于score=2，返回完整recheck供调用方区分。

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


## D3 第二轮：项级继承与合并检测

**行为变化**：to_refs保留项号，命中项号仅从检索chunk metadata继承；规则项与证据项不同记item_mismatch，证据无项号明确降级。保留多路JUDGE_MODE=multi，生产默认merged一次覆盖全部语义轴，缺轴为missing_axis。适配器记录每次调用耗时、token、attempt_count/retried。

**验证**：项级测试旧代码5失败/2通过，修复7通过；项继承旧代码cross_axis_rejected不符预期，修复通过。合并两测试先因缺接口失败，修复后agents83 passed。最终唯一验收audit_id=7：score0/incomplete=false，70346ms低于90秒；安全轴有效，功效轴两条合理候选因引用医美指南5.4（规则只声明广告法16.1）被严格拒绝，总体验收未全通过。无before_after/inducement误命中；未人工重跑。完整原始JSON/六样证据/归因见data/d3_final_acceptance_report.md。

**风险/技术债**：
| ID | 内容 |
|---|---|
| T-007 | 语义空闸：pattern由规则预填，模型可声称命中而无客观证据；候选方案回传判据短语并校验本轴词集，降级weak_evidence，不前置拒绝。 |
| T-008 | 索引正文仍含code前缀，稀释BM25权重；待未来重建时在摄取阶段剥离。 |
| T-009 | 成本只含A1判定调用，未含RAG rewrite/embedding。 |

**规则/评测**：未改规则内容或冻结评测；旧规范化测试更新项号输出断言，简称/中文数字/多引用/容错能力保留。


## D3 v0.3.2：法源补齐及版本化

**改动/独立依据**：仅efficacy_claim、safety_guarantee补医美指南第五条(四)，依据03原文及入库建议表“efficacy_claim+safety_guarantee”；cure_rate补医疗广告管理办法第7条(三)，依据08原文“宣传治愈率、有效率等诊疗效果的”。三条种子version=2；非放宽项级闸，不改评测。seed_rules追加变更快照并仅停用旧行，绝不覆盖历史内容。

**验证**：版本化RED为旧version1仍enabled1；修复后seed测试9 passed。生产预览pending3/total11；apply新增3/total14；三轴各v1停用/v2启用；重复apply新增0跳过11/total14。历史法源保持原样。第4次单次验收audit_id=8三项通过：功效/安全均有效，无before_after/inducement；原文定位[0,21]，两项ref精确归属；score0/incomplete=false/40311ms，10063输入/2109输出、cost0.013745元、A1调用1次无重试。完整原始JSON及六样证据见data/d3_v032_acceptance_report.md。未重跑。

**风险**：T-007语义空闸、T-008索引code前缀、T-009费用不含RAG继续保留。未改判定器代码或项级匹配粒度。

**规则/评测变更**：依据早于验收的原文和归档映射补齐法源；三个轴版本1→2且历史保留，评测集未改，不按模型输出临时放宽。


## D4 红队与报告
**改动**：scripts授权新增source/redteam_meta，默认预览幂等迁移；A3一次调用生成4轴×3违规档+4合规对照；A4顺序复用A1并写TP/FN/FP/TN/unjudged；A5 SQL聚合及模板；四个JWT接口；MCP保持6个。费用记录A1/RAG改写/embedding实际响应token，缺价null不冒充零。
**验证**：迁移前后3条均保留且source=manual；DDL证据data/d4_migration_before/after.json。迁移/生成/仓储/MCP/计量均先观察失败再实现；全量216 passed in 11.17s。唯一真实阶段E在A3生成调用失败，EmbeddingError：聊天服务请求失败或响应非法；没有生成样本、未进入A4。数据库scripts3/redteam0/audits7，均未新增红队审计；未人工重跑。失败证据data/d4_live_failure.json，日报data/d4_daily_after_failure.json为既有D3记录，不冒充D4结果。
**风险**：生成expected_violation是模型自报测试标签，不是官方锚点；embedding单价未知，total_cost=null。token占比不等价于费用占比，不能声称费用影响<0.3%。
**规则/评测**：A1判定逻辑、法规及冻结评测未改；本轮16样本仅内部比较，不具统计代表性。


## D4 读超时修复
**改动**：按统筹方已证实根因，不重复诊断；JUDGE_TIMEOUT默认180秒，urllib单次阻塞读操作而非总时长。ModelCallError分类HTTP/timeout/invalid_json/connection/network，EmbeddingError兼容继承；4xx1次、5xx2次、超时2次、连接3次尝试上限；脱敏日志含每次尝试耗时和错误类型，成功/失败均留明细，reasoning_chars仅计字符不改计费。
**验证**：8个transport测试先全部RED，修复8 passed；覆盖超时/非JSON/401/连接/兼容性/脱敏/reasoning/5xx及两urlopen配置一致。旧D4失败证据保留，新授权轮使用独立排他证据文件，不覆盖旧失败。
**风险**：reasoning_content仅记录长度，completion_tokens沿用供应商用量，重试失败尝试无usage仍不可计量。新授权真实轮A3成功16条，完成6条后终端工具420s终止进程；TP3/FN2/FP0/TN1/unjudged10，未重跑。实测embedding382/A169084token约0.553%，不支持<0.3%说法。完整证据data/d4_timeout_fixed_report.json。
**规则评测**：未改A1判定、规则、法规、索引或冻结评测集。


## D4 v0.4.1：按用途关闭判定思考、分批断点
**改动**：JUDGE_ENABLE_THINKING=false、REDTEAM_ENABLE_THINKING=true，显式配置且透传开关允许才加入参数；改写走EMBEDDING_ENABLE_THINKING，真正embedding端点不发送不适用字段。调用元数据写入audits.hits_json的call_metadata，不新增列。脚本默认4条一批、--resume读取run_id，数据库已有任意verdict均跳过；每条checkpoint、每批耗时。
**验证**：思考payload/调用字段/批执行旧代码4失败，修复后全量228 passed in 11.48s；生成保持true、false被网关忽略时明确报错另有fixture。真实新轮尚未执行。
**风险**：分批本身不减少总运行时间；本轮仍一次命令顺序跑完，不以重启规避420秒限制。旧失败证据不删不覆盖。
**规则评测**：未改A1判定规则、法规或冻结评测集，仅基础设施参数与执行恢复能力。
