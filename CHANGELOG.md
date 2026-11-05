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
**验证**：思考payload/调用字段/批执行旧代码4失败，修复后全量228 passed in 11.48s；生成保持true、false被网关忽略时明确报错另有fixture。新授权单轮rt_20261103_151028全部16条完成，TP7/FN5/FP0/TN4/unjudged0；审查平均5921ms，completion平均143.75，A1全部thinking=false/reasoning0；总141251ms，四批均<26秒。完整证据data/d4_thinking_off_acceptance_report.md。未重跑。
**风险**：分批本身不减少总运行时间；本轮仍一次命令顺序跑完，不以重启规避420秒限制。旧失败证据不删不覆盖。
**规则评测**：未改A1判定规则、法规或冻结评测集，仅基础设施参数与执行恢复能力。


## D4 v0.4.2：轴定义读取与目标轴矩阵
**改动**：A3从当前启用rules读取pattern/law_article并传入prompt，pattern_ref逐字匹配；不符记录invalid_axis_ref且不入矩阵。TP拆TP_axis/TP_other，报告新增轴级漏杀率，旧TP只按已存actual_axes重新解释不重判。
**验证**：3条新契约先因缺rules_loader/目标轴参数RED，修复GREEN；5格fixture含无效标签排除和两漏杀率，全量233 passed in 11.48s。
**历史保护**：授权保留34–37及全部审计，旧meta仅新增label_invalid及原因；不删除。新run只做inducement四条，旧22–33不生成/不判定/不改审计。主视图16，附视图20。
**风险**：pattern_ref是定义一致性检查，不等于模型语义证据；最终需人工论证容貌焦虑。唯一新增批次rt_20261103_152505_inducement完成：新3条TP_axis/1条TN，无invalid_axis_ref；旧12条保留，主视图TP_axis6/TP_other4/FN2/FP0/TN4，整体漏杀16.67%、轴漏杀50%。含生成71546ms，未重跑；完整证据data/d4_axis_alignment_report.md。


## D4 v0.4.3：确定性命中规则法源
**改动**：regex/keyword候选法条来自rules声明；检索只补chunk/item/ref，未召回也保留并标law_from_rule_table。LLM检索法条闸原样保留，pattern/项级归属仍检查，缺文档告警放行。
**测试**：核心旧代码0命中，新增5测试3失败/2通过；修复5 passed。全量一度因MySQL1041内存错误阻塞，恢复后238 passed in 12.07s。无规则/检索/阈值改动。
**验收范围**：仅新absolute_terms四条；其余12条沿用功效安全旧8条+上轮inducement4条；所有旧样本审计保留。真实单轮已执行：rt_20261103_155339_absolute_terms，42–45四条=3 TP_axis+1 TN；组合矩阵9/1/2/0/4，整体漏杀16.67%、轴级25%。证据data/d4_deterministic_report.md。
**风险**：正则覆盖缺口只报告，不自行补词或改规则。T-007/T-008保留；embedding未知不伪合计。


## D4 v0.4.4：embedding计价与索引元数据缓存

### 改动
- 本地.env与.env.example：EMBEDDING_PRICE_PER_M=0.5；text-embedding-v3文本输入，元/百万tokens，官方价2026-11（统筹方核实提供，非Batch File）。既有record_usage已读取此键，无需另加计费路径。
- indexed_docs增加lru_cache(maxsize=1)，顺序重复调用只读取一次Chroma元数据；LLM/检索/规则不变。
- 审查与红队成本注释按实际未知项生成，不再对已计价embedding宣称未计价；其他成本未知仍total=null。
- 不回填历史审计/脚本/证据；本轮没有调用任何付费模型，也没有重跑验收。

### RED/GREEN与实际输出
- 缓存RED：两次调用创建2次client，断言2==1失败；GREEN：indexed_docs calls=2; PersistentClient creations=1，结果集合一致。
- 费用配置RED：两条测试均因空单价失败；GREEN：1000 embedding tokens -> 0.000500元；judge=0.001、rewrite=0 -> total=0.001500元。
- 未知judge：embedding=0.000500、total=None，cost_note包含“仅 embedding 已计价，其他未知项不计伪合计”。
- 红队费用说明RED：两条测试发现硬编码“embedding未计价”；修复后通过。
- 全量pytest：243 passed in 11.76s。

### 外部资源创建点清单（本轮仅修indexed_docs）
|位置|生命周期与结论|
|---|---|
|backend/tools/audit_tool.py:indexed_docs|PersistentClient；本轮缓存函数结果，连续调用不再重复构造。|
|backend/rag/embedding.py:ChromaStore.__init__|每个实例创建PersistentClient；默认生产路径由retrieve.default_retriever的lru_cache(maxsize=1)保护。直接重复实例化仍可重复建资源，列T-011。|
|backend/db/session.py:engine|模块级create_engine，进程内复用连接池；非逐请求创建。|
|scripts/build_index.py|每次CLI执行创建ChromaStore，非请求热路径。|
|scripts/show_tables.py、seed_rules.py、migrate_rules_columns.py|每次CLI执行create_engine，已有dispose。|
|scripts/init_db.py|建库/建表分别create_engine，已有dispose。|
|tests/conftest.py|测试建库/建表/夹具create_engine，非生产路径。|
|tests/test_rules_setup.py、tests/mcp/test_tools.py|SQLite测试engine，已有dispose。|
|SentenceTransformer|仓库Python代码搜索无实例化或引用。|

### 技术债
- T-009 关闭（面向新记录）：embedding价格已接入，三项均已知时可合计；历史NULL不追溯。估算不是供应商账单，未来缺token或缺其他价格仍传播NULL。
- T-010 embedding模型可升级：qwen3.7-text-embedding-flash，0.125元/百万、128K上下文、100万免费额度至2026-11-30（统筹方提供，执行升级前需再核实）；需重建索引+重跑评测，勿在有交付压力时执行。本轮未升级。
- T-011 外部资源生命周期：直接重复实例化ChromaStore仍会构造client；后续统一资源工厂/关闭策略。indexed_docs缓存为进程级元数据快照，重建索引后需重启或cache_clear；lru_cache不保证并发冷启动只执行一次，不将本次顺序调用测试扩大为并发/内存泄漏根治证明。

## D6-b · 素材摄取层：图片/扫描件/语音/Office 全格式 + 溯源落库

**改动**：新建 `backend/parse/`（base 抽象+注册表 / documents 文档结构层 / media 模型层），支持 txt·md·csv、docx（正文真实顺序）、xlsx·xls（按文件头判格式）、pptx（含备注）、pdf（文字层；无文字层的页经 pypdfium2 渲染后走 RapidOCR）、海报图片（RapidOCR，按阅读顺序重排 + 平均置信度 + 低置信度警告）、录音（FunASR SenseVoiceSmall，懒加载，未装则如实报错并给出安装命令）；`.doc/.ppt/.odt` 等明确拒绝并说"另存为"。新增 `sources` 表与 `scripts` 四列溯源，原始素材按内容指纹落盘 `data/uploads/YYYYMM/`，**只在确认入库时写盘**。接口：`/scripts/import` 返回 kind/engine/confidence/warnings/items_detail；新增 `GET /sources`、`/sources/formats`、`/sources/{id}`、`/sources/{id}/file`（内联回看，越权 404）。MCP 工具增至 8 个：`parse_source`、`parse_document`（路径锁死 data/）。`backend/tools/extract_tool.py` 删除、实现迁入 parse；`backend/tools/ingest_tool.py` 承接落盘与溯源回填。**溯源由服务端重算**：客户端 items 只认文本，勾选项与文件解析结果对不上即拒绝入库。

**验证**：`python -X utf8 -m pytest tests -q` → **311 passed in 16.07s**（本轮新增 tests/parse 12 条 + tests/test_sources 11 条 + mcp 2 条）。真实 OCR 非假引擎：`python -X utf8 -m scripts.verify_parse` → poster.png `kind=image engine=rapidocr blocks=3 confidence=0.9973`，三行中文按阅读顺序还原（"双眼皮限时特惠 / 保证做完能往上走三个色度 / 全城最低价 术后零风险"），逐字回查断言全部通过。迁移：`migrate_sources_provenance --apply --show` 建表成功并打印前后 `SHOW CREATE TABLE`，复跑输出"跳过：sources 表已存在，scripts 溯源四列齐全"；MCP `--selftest` 列出 8 个工具。`pypdfium2 5.14.0` 渲染链路单测通过（未额外装渲染依赖）。

**遗留**：① ASR 依赖（funasr/modelscope/soundfile）按分工由作者本人安装，代码侧懒加载+能力探测已就绪，装上即生效；本机无 ffmpeg，mp3 靠 libsndfile≥1.1、m4a/aac 需 ffmpeg，已在错误信息里写清。② 解析是同步接口，海报数秒、录音数十秒，只靠大小/时长上限（文档 8MB、图片 12MB、音频 30MB / 300 秒）兜住，未做任务队列。③ 前端（S7）尚未接 `items_detail`/`/sources`，页面能力仍是"粘贴+文档"。④ 目录规模：`api/v1/resources.py` 307 行、`services/compliance.py` 300 行、`parse/documents.py` 300 行、`parse/media.py` 282 行、`parse/base.py` 278 行。resources.py 超 300 的理由按 CLAUDE.md §3.1 末档记录：`api/v1/` 已有 auth/resources/ai 三个实文件，再放第四个会破"每目录 ≤3 文件"，而把摄取路由并进 ai.py 属于职责错配；待 D6 前端联调后按业务域拆 `api/v1/ingest/` 子包。`scripts/` 目录 20 个文件为既有债务（迁移与一次性脚本堆积），建议后续合并为 `scripts/migrate/` 子包。⑤ 未打 tag、未 push：等 S7 前端联调通过一起走。

**规则/评测**：未改规则数据、法规正文与冻结罚单评测集。契约变动仅两处且均为能力扩展：`scripts/import` 响应新增字段（`items` 保持字符串数组，既有前端不破）；`tests/test_import.py` 原"图片不支持"断言改为"损坏图片报无法解码"（因为图片现在真的支持了）。

## D6-c · A1 第二个入口：按素材预审 + 流程图重画

**改动**：`AuditTool.review_source(source_id, client_id, limit=20)` —— A1 除"已存话术"外新增"整份素材"入口，内部调 MCP 工具 `parse_source` 重新解析原始文件，逐条走同一 N1–N9 判定路径并带回 `ref`/`confidence`/`warnings`；**不写 audits**（`persisted=false`），要留档仍须走入库 + batch。新增 `POST /api/v1/audit/preview-source`（商家账号强制本机构）。配套 `ingest_tool.source_owner()` 把归属校验收到"以库里的 sources.client_id 为准"，不接受调用方自我声明。`docs/flows/a1-合规审查智能体.md` 加"入口分流"与"N-1 素材归一"两节点、新增 §5 两入口对照表与三条取舍；PNG 已用 `scripts.render_flows --only a1 --layout both` 重出。`api_spec.md` 补 D6-c 节；`AGENTS.md` A1 流程行从"TODO（D3 补）"改为指向已定稿流程图（文档写着没做而代码已做，是本文件禁止的假契约）。

**验证**：`python -X utf8 -m pytest tests -q` → **317 passed in 20.01s**（新增 `tests/agents/test_source_entry.py` 6 条：入口分流、单条故障标 -1/incomplete 而非合规、截断必须显式 `truncated=true`、越权素材直接拒、切不出条目不算成功、解析警告必须传到调用方）。渲染输出 `OK docs\flows\img\a1-合规审查智能体.png 235,514 字节` 与 `-lr.png 233,912 字节`，共 2 张、失败 0。

**遗留**：① 预审路径的真实模型链路本轮未跑（用例替换了 `auditor.review`，因为 A1 判定本身已有 tests/agents 覆盖；接线一次真实端到端待前端联调时一起验）。② 新接口未接前端。③ `audit_tool.py` 291→295 行，仍在 300 内。

**规则/评测**：未改规则、法条正文与冻结评测集；无表结构变更。

## D6-d · S7 前端联调：喂素材、看溯源、回看原文件

**改动**：`api/http.ts` 新增 `requestBlob()`（绕开通用响应拦截器——它假定 `{code,msg,data}` 信封，Blob 会被判成"返回格式异常"；出错时把 blob 错误体读回 text 才能显示"素材已被清理"而不是"请求失败"；**不用 `?token=` 传令牌**，那会留在浏览器历史与访问日志）。`api/resource.ts` 接上 `parseCapabilities / sources / previewSource`，并把 DECIMAL 序列化成字符串这一事实写进类型（`SourceScript.confidence: number | string | null`，与既有 `AuditRow.cost` 同口径）。`views/merchant/Check.vue` 重写：`el-upload` 拖拽**多选**、accept 与"未启用能力"警告全部由 `/sources/formats` 生成、按文件分组预览、每条显示 `ref`（第几页/OCR块几/语音第几句）与识别置信度、入库按分组各一次 commit 再自动按 20 条分批审查。新增 `AuditResults.vue`（把结果表从宿主页拆出，Check 从 372 行降回 317）、`SourceDrawer.vue`（素材档案 + 原图/录音/PDF 内联回看 + 当场体检，Blob URL 在关闭与卸载时 revoke）、`views/source/SourceList.vue` 与 `/sources`、`/merchant/sources` 路由与菜单。平台端 `ScriptImport.vue` 的硬编码 accept 与"图片语音不支持"提示改为按能力清单生成（那是典型的"文档写着不支持、其实早就支持了"反向假契约）；`ScriptList.vue` 加「来源」列，点位置直接开抽屉。

**验证**：`cd frontend && npm run build`（vue-tsc --noEmit + vite build）→ **✓ built in 6.33s，0 error**；首轮报出 5 个真实类型错（clientId 重复声明、buildForm 参数、el-upload raw 的 File 超集、索引可能 undefined），逐个改到干净。后端起 uvicorn 后跑真实 HTTP 端到端：`GET /sources/formats` → `engines={ocr:true,asr:false}`，可上传 15 种扩展名且 `.doc/.ppt/.wav` 均不在其中；上传真海报 → **4.28s、engine=rapidocr、confidence=0.9973、3 条带 OCR块1/2/3**；`commit=false` 阶段 `scripts` 总数为 0（预览确实不写库）；`commit=true` → `source_id=1`、3 条话术带 ref 与逐块置信度；`GET /sources/{id}/file` → 37200 字节 **sha256 与上传一致**且 `Content-Disposition: inline`；改名重传同一张海报 → `duplicate_of=1`；提交一句海报上没有的话术 → **422「有 1 条内容与文件解析结果对不上」**。临时脚本与联调服务已清理（`taskkill /PID 15504 /T /F`），联调产生的商家账号 `e2e_*` 与 source_id=1/2 留在开发库未清（下次 seed 或手工清理，不影响结构）。

**遗留**：① 浏览器内的真机点验（拖拽、录音播放、抽屉动画）未做——本轮只做到类型检查、构建与接口级端到端；下一步人工过一遍。② ASR 依赖仍未装，`/sources/formats` 会持续报 `asr:false`，界面已如实显示"未启用"。③ 素材抽屉里"当场体检"未跑过真实模型（预审路径会真调 A1 判定，需要 JUDGE_API_KEY 与费用），按钮逻辑接口级已通。④ `Check.vue` 317 行仍略超 300，与 §3.1 末档同理由记录：SFC 含 template+script+style 三段，拆成两个组件会把一个交互流程割成两半，待 D6 定稿后按"预览区/操作区"再拆。

**规则/评测**：无规则、法条、评测集与表结构变更。

## D6-e · 收尾巴：清联调数据、摄取路由独立成子包、聚合入口归一

**改动**：① 清掉 D6-d 端到端脚本留在开发库的垃圾（3 个 `e2e_*` 商家账号与其机构、2 行 `sources`、6 行 `scripts`、2 个落盘素材文件；0 条 audits），删除前先盘点、删除后复核归零，非 `e2e_` 前缀数据一律不碰。② `api/v1/resources.py` 里为素材摄取新增的 117 行整段搬进领域子包 `backend/api/v1/ingest/{__init__,routes}.py`（307 → 190 行）：resources 的变化原因是"加一套 CRUD"，ingest 的变化原因是"加一种文件格式/引擎"，两者同处一文件时改一边会碰到另一边，且 resources.py 已因此顶到 307 行、越过 §3.1 上限。③ 聚合入口归一：删掉 2026-11-02 那次并发改动留下的第二套结构 `backend/api/v1/router/__init__.py`，唯一入口回到 `backend/api/v1/__init__.py` 并 include auth/resources/ingest/ai；`backend/main.py` 改 `from backend.api.v1 import api_router`。④ CLAUDE.md 的目录树、§3.1 目标结构与 §7.11 那条"结构漂移"记录同步更新（漂移已修，坑本身留着），`db/models.py` 注释"5 张表"改"6 张表"。

**验证**：`pytest tests -q` → **317 passed in 18.70s**（拆分后打真实 URL 的用例全过，等于证明路由一个没漏）。清点脚本两次运行输出对照：清理前 `账号 3 / 机构 3 / 素材 2 / 话术 6 / 落盘 2`，清理后全部归零。
一处如实更正：拆分后我一度以为"路由只剩 6 条"是事故，实际是 FastAPI 0.141 用惰性 `_IncludedRouter`、`app.routes` 不展开子路由，**不是 bug**；结论以测试套件为准，不以路由计数为准。

**遗留**：① `git push` 失败——`git@ssh.github.com: Permission denied (publickey)`，本机这把 SSH key 不被 `TS-DE/ComplianceGuard` 接受。四个提交（8fad9be / 18878b5 / 81b3bdc / 本次）停在本地 main，需要作者加部署密钥或改 HTTPS+token，我不能代填凭据。② `scripts/` 目录 20 个平铺脚本**本轮不动**：按 §3.1 应当子包化，但这些是 RUNBOOK 里要被手敲的执行入口（`python -m scripts.migrate_*` / `verify_law` 等），改名的连带面覆盖文档、README 与老师照着跑的步骤，交付前动它风险大于收益。建议交付后再并成 `scripts/migrate/`+`scripts/verify/`+`scripts/ops/`。③ 前端 `Check.vue` 317 行仍略超 300，理由同 D6-d 记录。

**规则/评测**：无规则、法条、评测集与表结构变更；接口 URL 与响应契约一字未改（纯文件位置重排）。

## D6-f · 流程图核对与总览图重做

**改动**：`docs/flows/README.md` 总览图重画并核对四处与代码不符的旧说法：MCP 工具 6 个 → **8 个**（补 `parse_source`、`parse_document`，节点名改用真实工具名而不是"法条检索"这种意译）；MySQL 5 张业务表 → **6 张**；使用者只有"运营/法务" → 补上**商家（自助端）**；新增「素材摄取层 backend/parse」子图（文档结构 / OCR / ASR / 溯源四个节点）与 `data/uploads` 原件存储。删掉一条不成立的旧连线 `复核工具 → 法规归档`（`audit_recheck` 走的是向量检索那条路，不直接读 Markdown 归档）。铁律表从四条补到五条（新增"溯源以服务端为准"）。A1 职责行标注"入口有两个"。a2/a3/a4/a5 四张分图经核对无需改动——A2 那条"score=2 或命中数下降"与 `agents/compliance.py:305` 的实现一致，是逐行对过而不是照着文档信。§四 的尺寸表改为**实测值**（PIL 读 PNG 尺寸），并写明总览图源码本身是 `flowchart LR`，`--layout both` 对它产出同一张图，避免有人以为渲染坏了。

**验证**：`python -m scripts.render_flows --layout both` → 12 张图，首轮成功 10 / 失败 2（a1 两张因 DNS 抖动 `getaddrinfo failed`），`--only a1 --layout both` 重试后 2/2 成功；最终 12 张全部为本次渲染产物。实测尺寸示例：A1 竖版 632×3686、横版 4603×421；总览 3313×1429（td/lr 相同，原因如上）。

**遗留**：① 横版 4603×421 在 16:9 页面上要缩得很小才可读，答辩若用横版建议现场放大或用 Mermaid 源码投屏。② 未做视觉复核（我只验证了"渲染成功+尺寸属实"，图里的连线是否美观没人眼看过）。

**规则/评测**：无规则、法条、评测集与表结构变更；纯文档与图片。

## D6-g · 语音准备到位（仍卡在依赖），顺手补掉一处假契约

**改动**：① 能力探测原来只看 `funasr` 装没装，**没看音频能不能解码**——模型在、解码器不在时界面仍会把 `.wav` 放进 accept，用户传上去才发现"打不开"，这正是本项目最忌的假契约。新增 `base.audio_decoder_available()`（soundfile 或系统 ffmpeg），`engine_available("asr")` 改为"模型 **且** 解码器都在"才算可用；解码失败的报错也改成直接给出 `pip install soundfile`，不再只说"未安装 ffmpeg"。② 用 Windows 自带中文 TTS（Microsoft Huihui）生成真实语音样本 `data/verify/talk.wav`：22050Hz / 单声道 / 16bit / 10.23s / 三句话（含"保证做完能往上走三个色度"），供装完依赖后一条命令验收。③ RUNBOOK 新增「语音（ASR）验收步骤」：装依赖 → 看 engines 翻 true → `verify_parse data/verify/talk.wav`，并写明通过判据是**转写带标点**（没标点切不开句子，算失败），附可重造样本的 PowerShell 片段与两个 API 坑（`System.Speech` 无 `SpeakToFile`、`SetWaveFormat` 非公开）。④ `parse/base.py` 从 319 压到 308 行。

**验证**：`pytest tests/parse tests/test_sources.py tests/mcp -q` → **62 passed in 11.36s**（新增 2 条探测用例：解码器缺失时 asr 必须 False、本机实测 `.wav/.mp3/.m4a` 全部 available=False）。样本参数用 `wave` 模块实测打印：`采样率 22050 声道 1 位深 16 时长 10.23s`。能力探测本机输出：`engines {'ocr': True, 'asr': False}`。

**遗留**：① **ASR 仍未跑通**——按分工语音依赖由作者本人安装，我不代装；装完照 RUNBOOK 三步验收即可，代码侧不需要再改。② `base.py` 308 行仍超 §3.1 的 300：已按"先按职责拆"试过（把能力探测移进 media.py 会让那边从 291 涨到 326，更糟；再拆一个文件会破"每目录 ≤3 文件"），继续砍行数只能删"为什么"注释，本末倒置，故按末档在此记录理由。③ 推送仍被 SSH 凭据挡住。

**规则/评测**：无规则、法条、评测集与表结构变更。

## D6-h · 环境体检：依赖其实一直躺在 C 盘 user-site

**改动**：作者问"你用的是哪个 python"，一查发现问题不在解释器而在包。解释器确实一直是 `E:\Anaconda_download\envs\py312_env\python.exe`（3.12.13，PATH 首位；C 盘的 py311 与 WindowsApps 只是排在后面没被用到）。但 `C:\Users\<user>\AppData\Roaming\Python\Python312\site-packages`（user-site）也在 sys.path 且**优先命中**：`SQLAlchemy` 与 `PyMySQL` 只装在那里，E 盘 env 里一个文件都没有——`requirements.txt` 钉了版本、`pip` 报 "Requirement already satisfied"，CLAUDE.md §9 写着"已确认可用"，全都是真的但都不是在 env 里。用 `--ignore-installed` 把 `SQLAlchemy==2.0.52 / PyMySQL==1.2.0`（连带 greenlet、typing-extensions）真正装进 E 盘 env；`.gitignore` 补 `.qwen/`（Agent 的本地工具授权配置被 GitHub Desktop 当成待提交改动列了出来，不该进仓库）。CLAUDE.md §9 增写 user-site 污染事实与两条硬规矩：装包后必须用 `import x; print(x.__file__)` 验来源、启动与测试统一带 `PYTHONNOUSERSITE=1`。

**验证**：`set PYTHONNOUSERSITE=1&& python -m pytest tests -q` → **319 passed in 17.50s**，即关掉 C 盘用户目录后该 env 能独立跑通（这是"环境自足"的直接证据，之前只是碰巧靠 C 盘兜着）。加载来源实测：`sqlalchemy 2.0.52 <- E:\Anaconda_download\envs\py312_env\Lib\site-packages\...`。
一处自我更正：我一度以为 `pymysql.__version__` 报 2.2.8 是撞上同名抢注包，读源码后确认是 PyMySQL 1.2.0 自己为兼容 mysqlclient/Django 导出的别名（`__init__.py:52` `VERSION=(1,2,0,"final")`、`:58` `__version__="2.2.8"`），**不是安全问题**；结论以读文件为准，不以属性名猜测为准。
远端状态核实：GitHub API `repos/TS-DE/ComplianceGuard/commits/main` → `0f58a666e72e`，作者用 GitHub Desktop 推的 5 个提交确实都在远端（我 shell 的 SSH key 仍被拒，故以 API 为证据）。

**遗留**：① C 盘 user-site 里那份 SQLAlchemy/PyMySQL 副本**我没删**——删它会影响这台机器上的其他项目，属系统级改动，需作者本人决定；带 `PYTHONNOUSERSITE=1` 即可绕开。② README/RUNBOOK 的启动命令尚未统一加该变量（规矩已进 CLAUDE.md §9，命令模板待下一轮同步）。

**规则/评测**：无规则、法条、评测集与表结构变更；仅环境事实与忽略规则。

## D6-i · 命令模板补环境开关，HARNESS 六组件按实测改状态

**改动**：① README「怎么跑」与 RUNBOOK §1 启动顺序都加了第 0 步 `set PYTHONNOUSERSITE=1`，并在 README 里补上"装完包必须 `print(sqlalchemy.__file__)` 验来源"与 `migrate_sources_provenance --apply` 一步（此前新机器照 README 跑会漏掉溯源迁移）。② `HARNESS.md` 六组件矩阵从"规则已写"改成"跑过没有"：②补 8 个 MCP 工具与 A1 双入口的证据路径；④ 用本轮 `sources` 迁移作为 §7.10 硬规则的一次真实执行记录（预览/apply/复跑跳过/前后 SHOW CREATE TABLE）；⑤ 用"能力探测假契约→修正→2 条测试→SKILL S10"作为一次真实反馈闭环；⑥ 列出本轮删并的 5 处过时说法。③ 只标到 🟡 并写明缺哪半：编码 Agent 侧记忆实测存在（3 条），统筹方约定的 `~/.hermes/MEMORY.md` **实测不存在**。④ 里那句"被拦下的 DROP TABLE"没勾成完成——本轮根本没写破坏性 SQL，只能算"未发生"，不吹成拦下过。§四 待补证据勾掉 3 项、留 3 项并逐条说明为什么还不能勾（含 Coze 那项明确写"未做，需作者提供发布地址"）。

**验证**：`git remote -v` 确认作者已把 origin 从 SSH 改成 HTTPS，我的 shell 现在能 fetch；`git log origin/main` 显示远端已到 `ab63693`（作者自提的 test_redteam 桩件修正），我的 `0cce3c4` 也确实在远端。`~/.hermes/MEMORY.md` 用 `if exist` 实测：不存在。

**遗留**：① 记忆路径两套并存（`.qwen` 与约定的 `.hermes`），D7 前需二选一，属文档债。② `ab63693` 的提交信息是 Desktop 默认的 "Update test_redteam.py"，与项目"小步语义化 commit"的规矩不符；**已推送的历史不该改写**（要改就得 force-push，风险大于收益），建议后续提交按语义化写。③ 真机点验与 ASR 仍等作者。

**规则/评测**：无规则、法条、评测集与表结构变更。

## D6-j · A5 日报补素材形态分布：这批结论是从什么材料里读出来的

**改动**：`RedteamRepository.daily()` 增加 `by_source` 分桶（`image / pdf_scan / pdf_text / docx / sheet / slides / audio / text / no_material`），沿用了与 `by_axis` 完全相同的 `criteria`，因此商家端的机构裁剪自动生效、不另开口径。实现走 `Audit → Script → LEFT JOIN sources` 后 `group by`：**必须 outerjoin 并把无 source 的行标成 `no_material`**——用 inner join 会把手工录入与红队样本静默丢掉，日报会呈现出"我们所有结论都来自上传素材"的假象。A5 的铁律照旧：只做已有记录的聚合，模型不参与算数。前端商家工作台（Portal）新增「今日结论来自哪些材料」卡片，kind 标识符统一映射成中文（商家看不懂 `pdf_scan`）。写 api_spec 时又逮到一处陈旧说法：`api_spec.md` §D4 还写着「MCP 仍 6 个」，实际已是 8 个，一并改正。

**验证**：`set PYTHONNOUSERSITE=1&& python -m pytest tests -q` → **320 passed in 17.82s**；新增用例 `test_daily_report_breaks_down_by_material_kind` 断言三桶各 1 且 `sum(by_source.values()) == total - incomplete`（分桶之和必须等于已判定数，多算少算都会在这里露馅），并断言别家机构的 client_id 查出来是空字典。前端 `npm run build`（vue-tsc + vite）→ **✓ built in 6.16s**。

**遗留**：`by_source` 目前只在商家工作台露一张卡片，平台端 Dashboard 与导出报告模板尚未使用；等真机点验通过后一起接。

**规则/评测**：无规则、法条与冻结评测集变更；无表结构变更（只读聚合）。

## D6-k · 上传前的本地预判：能力没装就别白传一次

**改动**：读 Element Plus 源码（`upload/src/upload-content.vue` 的 `uploadFiles`）确认了一件事——**`accept` 只作用于文件选择框，拖拽进来的文件一律不过滤**。所以拖一个 `.wav` 或 `.doc` 会整份上传到后端才拿到 422：30MB 的文件白传一次，用户等半天只看一行红字。新增 `frontend/src/utils/parseAccept.ts`，把三件本来各写一份的事收成一处：`acceptOf()` 生成 accept、`missingEnginesOf()` 生成"未启用能力"提示、`refuseReason()` 在发请求前给出具体理由（无扩展名 / 压根不支持 / 能力未启用 + 该装什么）。商家端 Check 与平台端 ScriptImport 同时改用它，顺带消掉两处 accept 逻辑的重复实现。能力清单没拉到时返回 null 交给后端判——前端不瞎猜，也不假装支持。

**验证**：`npm run build`（vue-tsc --noEmit + vite build）→ **✓ built in 6.03s**。第 4 条点验的预期行为已按此实现：拖入 `.wav`（本机未装 funasr）应立刻在分组卡片上出现「语音转写未启用：需要语音引擎（funasr + SenseVoiceSmall 约 500MB，落 data/models）与音频解码器（soundfile 或 ffmpeg）」，**不发请求、不留空白**。

**遗留**：`Check.vue` 324 行仍超 §3.1 的 300。本轮**刻意不做**拆分（把分组卡片抽成子组件会改动刚写完、还没经人眼点验的交互代码，风险大于收益）；等 7 条点验通过后，按「预览区/操作区」拆一次并单独提交。

**规则/评测**：无规则、法条、评测集与表结构变更；纯前端交互。

## D6-l · 预检逮到一处真越权：红队四个接口对商家开放

**改动**：点验前先跑了一遍无头预检（注册临时商家 → 直接 curl 各接口 → 用完删号），发现 **`GET /redteam/options` 对商家返回 200**，而它的响应体里带着每条轴的 `pattern / law_article / detector / version`——等于把判定规则本身交给被审查方，违反 CLAUDE.md 铁律与 AGENTS.md「商家不应看到或改动判定规则」。前端菜单只是不显示，直接请求接口照样拿得到。修法：`ai.py` 引入 `require_platform`，对 `/redteam/run`、`/redteam/{run_id}/gaps`、`/redteam/options`、`/reports/redteam/{run_id}` 四个端点统一拒商家（403）；`/reports/daily` 保持开放但按机构裁剪（商家要看得见自己的数），`/law/article` 保持开放（商家核对法条本来就该能看）。`api_spec.md` §D4 补写这条权限边界。

**验证**：新增回归 `test_merchant_blocked_from_redteam_apis`（四个端点逐一断言 403 且消息含"管理员"）；`set PYTHONNOUSERSITE=1&& pytest tests -q` → **321 passed in 16.88s**。预检脚本其余输出（用完已自清理，临时账号与机构删除）：
`engines={'ocr': True, 'asr': False}`、音频可传 False、上传 `.mp3` 后端兜底 422 并给出 `pip install soundfile`、粘贴 3 条预览 `count=3 created=0`、商家 `GET /rules` 403、`/reports/daily` total=0 且 `by_source={}`、历史 run `rt_20261104_ddaa57ff` 矩阵 `{TP_axis:11, TP_other:0, FN:1, FP:0, TN:4, unjudged:0}`（走仓储直查，一分钱没花）。

**遗留**：① 粘贴文本切出的条目 `ref` 为 `null`（粘贴没有页/段结构可依），界面会隐藏位置徽章——不是丢失，但商家若想"第 2 行"这种定位，需要给粘贴也做行号，待定。② 预检只覆盖 API 面，浏览器交互（菜单切换、剪贴板、内联预览）仍需人眼，正是下面 7 条点验要做的。

**规则/评测**：无规则、法条与冻结评测集变更；无表结构变更。权限边界收紧属于契约变更，已同步 `api_spec.md`。

## D6-m · Harness 组件③ 落地：~/.hermes 记忆文件建成，内容全部可复核

**改动**：按作者要求建立 `~/.hermes/MEMORY.md` 与 `~/.hermes/USER.md`，把"跨会话不丢项目状态"从约定变成实物。**内容一律取可核对事实，不写"打算这么做"**：端点清单是 `GET :8000/openapi.json` 实测的 **39 个**（分组列出并标出权限边界），版本是 `settings.app_version=0.1.0` 与前端 `0.5.0` 原样记录（顺带暴露出"后端版本没随阶段 bump"这条遗留），测试数是实跑的 `321 passed`，遗留 BUG 9 条每条带状态与出处。USER.md 沉淀作者偏好与工作方式（中文注释、Pydantic V2、禁裸 except、单线程禁委派、C 盘禁装、复用开源不造轮子、**对假契约零容忍**、破坏性操作先问）。`HARNESS.md` 组件③ 由 🟡 转 ✅ 并给出证据路径，§四 对应项勾掉。

**自查修正**：改完组件③ 才发现 §二 的表格还写着"实测 2026-11-04 尚不存在"——那是本轮早前的状态，文件建好后就成了过时说法。本项目最忌"文档写着、跑起来不是"，所以同一轮把它改成"已建立"，并补一行变更记录。

**验证**：两份文件写入后目录实测存在；其中引用的数字全部来自本轮实跑命令（`openapi.json` 端点计数、`pytest`、`git log`），非手抄。`HARNESS.md` 六组件现为 ①②③④⑥ ✅、⑤ 🟡（红队漏杀→规则候选→入规 仍缺一次真实闭环，明确标着没装成）。

**遗留**：记忆两套并存（`.hermes` 与 Agent 自己的 `.qwen`）这件事已写进 MEMORY.md 遗留表，交付后统一。

**规则/评测**：无规则、法条、评测集与表结构变更；无代码变更。

## D6 · 判定分级闸：区分「描述」与「承诺」（2026-11-04）

**改动 / 行为变化**：`efficacy_claim` 等硬轴不再非黑即白。新增 `N7.5 分级闸`：
命中且**不含承诺词**（保证/一定/彻底/百分百/绝对/永不/无效退款/包见效）但**含模糊限定词**
（可能/大约/通常/一般/因人而异/个体差异/应…）的硬命中，降级为 `soft` 并标记
`downgraded=true` 与 `downgrade_reason`；分数由 0 变 1，界面显示「疑似违规 · 建议复核」。
判据放在 `core/constants.py` 的 `COMMITMENT_WORDS` / `HEDGE_WORDS` 与代码里，
**模型只举证、不分级**（守住"分数由代码算"）。
同时修正 `_score`：被降级的命中不计入"多处违规"累加，否则两句独立预后描述会凑成违规。
顺带修 `invalid_quote` 误丢：引文先按同一 NFKC 规则归一后再定位，
模型把全角标点写成半角时不再被判成编造引文。

**实际验证**：真实模型跑三条同义改写 ——
「皮肤愈合后，应更显光滑。」→ score=1（疑似）、downgraded=true；
「可能需要大约三个月时间才能恢复正常肤色」→ score=1、downgraded=true；
「保证三个月恢复正常肤色」→ score=0（违规）、未降级。
接口返回可查（`POST /audit/batch` 实测 HTTP 200）。全量 `pytest tests -q` → **325 passed**。

**风险 / 遗留**：降级只影响严重度、不取消命中，因此漏杀风险有限（商家仍被提示）；
但 `HEDGE_WORDS` 含「应」这类高频字，理论上可能把个别真承诺降级，
后续应把误降样本收进留出集观察。单句判定仍有局限：
上下文把时间/效果绑成招揽卖点（"三个月见效，无效退款"）时需结合整段判断，
当前仅按引文所在句判断。

**规则 / 评测**：未改 `rules` 表数据与法条归档；新增 4 条分级用例
（测试号见 `tests/agents/test_compliance.py`）。两条真实误杀样本
（「皮肤愈合后，应更显光滑」「可能需要大约三个月时间才能恢复正常肤色」）
已作为回归样本固化。

## D6 · L3 人机回环：待复核队列与人工裁定（2026-11-05）

**改动 / 行为变化**：补上缺失的 L3。此前 `score=-1` 只在界面挂"待人工复核"标签，
没有队列、没有裁定入口、没有回流，标签挂着没人能处理。
新增 `audits.review_status/reviewed_by/review_note/reviewed_at` 四个字段；
**入队口径**：`incomplete=1`、`score=1`、或命中含 `downgraded=true` → `pending`，
硬违规与合规 → NULL。三个接口 `GET /audit/review-queue`、
`POST /audit/{id}/review`、`GET /audit/review-stats`。裁定为终态，
重复裁定返回 422；越权按 404。一致率分母只算已裁定记录。
前端新增 `views/review/ReviewQueue.vue`，平台端与商家端各一条入口。

**实际验证**：迁移预览→执行→幂等复跑输出"跳过：audits 已有全部复核字段"；
`SHOW COLUMNS FROM audits` 见四个新列；`--backfill` 把 15 条历史记录回填为 pending。
真实 HTTP 闭环：造「皮肤愈合后，应更显光滑。」→ 审查 score=1 → 队列查得 total=1 →
裁定 dismissed 落库（reviewed_at 有值）→ 重复裁定 422「不可重复裁定」→
统计 `{pending:0, confirmed:0, dismissed:1, judged:1, agree_rate:0.0}`。
`pytest tests -q` → **332 passed**（新增 `tests/test_review.py` 7 条）。

**风险 / 遗留**：回填只写 pending、不覆盖已有裁定，可重复执行。
裁定不可撤销是刻意取舍（避免人工结论被无痕改写），后续若要支持改判需引入
独立的重裁记录而不是就地覆盖。人工复核结果目前只用于统计一致率，
**尚未自动生成规则候选**——这是组件⑤的下一步，需要人工审核后才允许 bump 规则版本。

**规则 / 评测**：未改 `rules` 数据与法条归档；新增表字段与迁移脚本，
`db_schema.md` 同步记录迁移链路。
## FE-A1 · 前端设计系统与外壳（换皮不改业务逻辑）

**改动**：建立 `frontend/src/styles/tokens.css`（冷灰档案纸四档底色 + 四个风险语义色 + 8pt 栅格 + 唯一一档 3px 圆角 + 衬线引文/无衬线界面的字体分工）与 `base.css`（在这一处把 Element Plus 主题变量映射到 token，组件里不许再写色值；附 `prefers-reduced-motion` 与 `:focus-visible` 兜底）。新建 `components/` 按类别分子目录、每目录 ≤3 个 `.vue`：`risk/RiskBadge`、`risk/ScoreRing`、`risk/HitCard`、`data/StatCard`、`data/EmptyState`、`data/DiffView`、`layout/StepProgress`。判定→视觉的唯一出口是 `utils/risk.ts::riskState()`：页面里再出现 `score !== 0 ? 绿 : 红` 就会把"判定未完成"显示成合规，这是本项目最贵的一类错，所以宁可多一层映射也不允许各处自己判断。`ScoreRing` 刻意不做成百分制——`score` 取值域是 -1~2（db_schema.md 的 CHECK 约束），渲染成"73 分"就是凭空造量表。新增依赖 `diff@9`（jsdiff，词级差异；差异算法错得很安静，不自己造）。外壳改纸白＋边线、导航用标题首字作字标（**不装图标库**：本轮只允许 ECharts 与 diff 两个新依赖）、顶栏去掉与页面 h1 重复的小标、免责声明常驻侧栏底部；`go()` 显式跳转与 `router-view :key` 两处旧逻辑原样保留（它们是"点了没反应"踩坑后加的）。`frontend/README.md` 写下设计主张与七条验收标准，后续改版以此为准。

本轮**未动任何业务页面内部逻辑**，导航项也按现状保留（A2 才压缩商家端到 4 项）。

**实际验证**：`cd frontend && npm run build`（`vue-tsc --noEmit && vite build`）→ **✓ built in 6.12s，零类型错误**；产物里 `ReviewQueue/Check/ScriptList/Portal` 等 11 个页面 chunk 全部正常产出，说明旧页面在新主题下仍可编译挂载。`set PYTHONNOUSERSITE=1&& python -m pytest tests -q` → **332 passed**，与本轮开工前持平（前端改动不该影响后端，用测试确认没有误碰）。
构建首轮真实报错并已修：`ScoreRing` 里误写 `transform` 重复属性 + 无效 CSS 属性 `dasharray`；`DiffView` 里 `as const` 用在三元表达式上（TS 不允许）；`ScoreRing` 的填充比例数组 `[1/3,2/3,1]` 与索引 `(2-score)` 方向反了，会把"合规"画成最空的环——已改为 `[1,2/3,1/3]` 并在注释里写明映射。

**风险 / 遗留**：① "无控制台报错、页面渲染正常"只验证到编译与构建层面，**浏览器里的人眼确认仍缺**（A1 验收标准第 1 条要求的就是这一项）；请在重启 vite 后走一遍 8 个页面。② 旧页面各自的 scoped 样式仍写着 EP 变量与少量硬编码色（如 Portal 的 `.stat.danger`），在新主题下颜色语义是否仍自洽，需要肉眼过一遍再决定是逐页清理还是留到 A2/A3 改写时一并处理。③ ECharts 未装（等 A4 趋势图真要用了再登记）。

**规则 / 评测**：无规则、法条、评测集与表结构变更；后端零改动。新增前端依赖一项已在此登记。

## FE-A3 · 检查页双栏 + 原文高亮 + 条款原文 + 采纳改写

**改动**：`views/merchant/Check.vue` 重做为三段工作台（喂素材 → 核对切分 → 看结论），工具条 sticky、步骤条可点回任意一步，长文档不用再滚到底找按钮。左栏 `components/text/SourceText.vue` 显示**整篇原文**并按需高亮：预览阶段画「切分边界」（中性描边，不占风险语义色，避免预览看起来像已经判过），结果阶段画命中区间（朱红=hard、赭黄=软/已降级、石墨=未完成），点高亮联动右栏、点右栏滚到原文。**没有把切分碎片当原文展示**——那正是「找不到位置」的根源。
右栏 `parts/ResultPane.vue`：每条固定四件事（片段±20字上下文、法条原文、判定理由、风险等级）；法条原文按需调 `/law/article`（只读本地归档，不花钱），**取不到就只显示条号、不编造正文**；「采纳改写」调 `/audit/{id}/rewrite` 后用 `DiffView` 展示词级差异并标二次过审结果。
新增 `utils/locate.ts`：忽略空白的下标映射 + 顺序游标定位。后端只加一个展示字段 `full_text`（`ingest_tool.preview()`，不动任何既有字段语义），`api_spec.md` 已记账并写明「话术不一定是原文的字面子串，前端必须用忽略空白的定位」。目录规模补齐：`AuditResults.vue` / `SourceDrawer.vue` 移入 `views/merchant/parts/`（原目录 4 个 vue 违反每目录 ≤3），`ScriptList`、`SourceList` 引用同步。`resource.ts` 的 `Hit` 类型补 `original_quote/start/end/detector/status`（后端早就算好了，前端类型缺声明时会静默是 undefined）。主题线索只取解析首行并标注「非模型提炼」，取不到就显示「主题识别未启用」。

**实际验证**：定位算法先用真实解析产物验过（docx 两段：一段含段内换行、一段是另一段的尾巴）——
朴素 indexOf：长句 -1、短句 3（错）；忽略空白但无游标：长句 [3,14] 对、短句 3（错，落在长句内部）；忽略空白 + 顺序游标：[3,14] 与 [18,23] 全对。
该不变量已固化成 `tests/parse/test_documents.py::test_pieces_are_locatable_in_full_text_ignoring_whitespace`，**含「不带游标必须指错」的反向断言**，防止以后有人图省事把游标删掉。
`npm run build`（vue-tsc --noEmit + vite build）→ ✓ built in 6.34s，1769 modules。构建首轮真实报错 6 处全部修净：移动文件后两处 `../../api/resource` 相对路径、`SourceList` 的抽屉路径、`ImportResult` 缺 `full_text` 声明、`marks` 用 filter 类型谓词收窄导致联合类型不匹配（改显式循环）、`<script setup>` 里 `export interface` 不被 Vue 允许（类型挪进 `components/text/marks.ts` 与 `parts/types.ts`）。
`set PYTHONNOUSERSITE=1&& pytest tests -q` → **333 passed in 18.77s**。

**风险 / 遗留**：① **A3 验收要求的那条真人路径我没跑**：「含 2 处违规的长文案 → 高亮 → 点条 → 看条款原文 → 采纳改写 → 看 diff」需要真模型（API key 与费用）与浏览器，按你的排期放在「我审计 → 你开浏览器验 A3」那一步。② 定位仍可能失败的两种真实情形：同一句在原文跨段重复出现（切分层已去重同条重复，跨段同文仍会撞，此时按游标顺序取第一个，可能与后端当时审查的那一实例不同一）、OCR 把花字识别成近形字使引文与原文有字差。两种都会走「位置未知」并列出引文，不静默。③ 主题线索是首行摘录不是提炼；要真主题需另接一次轻量模型调用，属新增成本，没擅自加。④ `Check.vue` 446 行：页面把三段的编排都揽在自己身上，A2 合并导航时把输入段与预览段拆成 `parts/` 下两个子组件。

**规则 / 评测**：未改规则数据、法条正文与冻结评测集；无表结构变更。接口新增展示字段 `full_text`，已在 `api_spec.md` 记账。

## 批次1-T1 · 否定语境闸：断言词被否定修饰时不再当承诺

**改动**：`core/constants.py` 新增 `NEGATION_WINDOW=6`、`NEGATION_WORDS`、
`CONTEXT_HEDGE_WORDS`、`RECHECK_WORKERS=4`、`BATCH_AUDIT_WORKERS=4`、
`RECHECK_CONTEXT_CHARS=200`（词表与上限集中在 constants，不散进判定器——SRP）。
`agents/base.py` 新增 `mark_hit_context()` 与 `ContextGateDetector` 装饰器，注册表里
keyword/regex 改为包装态：判定链路里没加一条 if-else，将来新增检测手段自动获得同一层标记（OCP），
内层检测器仍可单独实例化、异常语义不变（LSP）。
`agents/compliance.py::downgrade_descriptive_hits` 把否定判断挪到承诺词判断**之前**：
`永久` 同时是命中词和承诺词，旧顺序下「可能不是永久性的」必然保持硬违规——
这是原始缺陷的真正成因，不是模型判错。命中一律**只标记不丢弃**（丢弃会把真违规一起吞掉），
标记与 `needs_recheck` 随 hit 进 traces 供复核与审计使用。

**实际验证**（`tests/agents/test_context_gate.py`，11 条）：
「磨皮术的效果可能不是永久性的」→ 命中 `永久` 且 `negated_suspected=True / negation_signal=不是`，
分级闸后 severity 由 hard 变 soft、`downgraded=True`、`needs_recheck=True`，理由写明"断言词被否定结构修饰"；
反面对照「保证三个月恢复正常肤色」仍为 hard（否则语境闸就成了放行开关）；
「如果不做术后护理，效果永久」→ `context_hedge=True`，严重度不动但必须进复核队列；
「不用担心。效果永久」→ 否定词隔句，不标记（窗口生效）；
裸 `RegexDetector` 不带标记、`DETECTORS['regex']` 是装饰器实例（职责分层可验证）。
`set PYTHONNOUSERSITE=1&& pytest tests -q` → **344 passed in 16.73s**（333 + 11，无既有用例改动或删除）。

**风险 / 遗留**：① 本轮开发中我自己写出又删掉两处坏代码（`_sentence_span` 里缠绕的生成器表达式、
分级闸里 `or True: pass` 死行），都已在提交前清掉——记在这里是因为它们说明了"能跑通不等于写得对"。
② 否定词表含单字（不/非/无/未/否/勿/难），窗口 6 字仍会误标少量正常句
（如"无创永久脱毛"里 `无创` 会标记 `永久`）：标记只影响是否送复核，不直接放行，
因此代价是多一次复核而不是漏判；这类样本应在 T2 复核提示词里显式覆盖，后续按误标率收窄词表。
③ `needs_recheck` 目前只打不用，消费方是 T2 整篇复核。

**规则 / 评测**：未改 `rules` 表数据与法条正文；无表结构变更。
判定行为变化一处：命中片段左侧 6 字内出现否定词时，硬命中降级为疑似（score 0→1）并进入复核队列。

## 批次1-T2 · 整篇复核 + 语境标记移到汇合点

**改动**：新增 `backend/agents/audit/recheck.py`（子包存在的唯一理由：`agents/` 已占满
"每目录 ≤3 实文件"，而复核必须能独立审计与独立测试）——`recheck_hits()` 把命中所在上下文
（前后各 `RECHECK_CONTEXT_CHARS=200` 字）交给模型二次判读，**处置权在代码**：
`confirm` 保持或升回、`downgrade` 降 soft 并写理由、`dismiss` 移出 active 命中但强制留痕
`traces[status='dismissed_by_context']`；越界 verdict、错引 quote、序号越界一律不采纳并记
`recheck_rejected`；调用失败/JSON 不可解析**不改原判**只记 `recheck_failed`/`recheck_unparseable`。
`compliance.py` 接入 N7.6（在分级闸之后、聚合算分之前），并按 §六.2 的时延压力把复核范围
收紧为**只复核有语境信号的命中**，无信号记 `recheck_skipped=no_context_signal`。
`/audit/batch` 由串行改为 `ThreadPoolExecutor(max_workers=BATCH_AUDIT_WORKERS=4)`：
结果按 script_ids 原序回填、每个任务自带 Session（Session 非线程安全）、越权校验仍串行先做、
单条失败仍只标该条；"话术不存在"保持原来的逐条 error 行为——那是我没被要求改的既有契约，
第一版我顺手改成了整批 404，发现后撤回。

**过程中发现并修掉的三个真问题**（都不是"跑不通"，而是"跑通了但结果不对"）：
1. **语境标记只包 keyword/regex 不够**：真实样本里 regex 的"永久"命中被复核驳掉了，
   活下来的是 LLM 判的 `efficacy_claim` 硬命中，而它从没过语境闸 → 整条仍结案为硬违规。
   改为在 N6 候选汇合点统一 `mark_hit_context`，对全部检测手段生效（真 OCP）。
2. **否定词可以在引文内部而不只在左侧**：模型给的引文常是整短语「可能不是永久性的」，
   只看左侧 6 字完全漏掉。窗口改为"左 6 字 + 引文自身"。
3. **词表降级必须可被复核升回**：只降不升会让一次误标（"无创永久脱毛"里的"无"）
   永久削弱真违规。分级闸记 `severity_before_gate`，复核 `confirm` 时升回 hard
   （方向只朝严不朝宽），记 `context_restored`。
另修一处我自己写下的**偶发用例**：`test_duplicate_upload_is_pointed_out` 原先两次调用
`_docx()` 生成"同样内容"，而 python-docx 把创建时间写进 docProps → 跨秒时字节不同、指纹不同、
判重不成立。改为复用同一串字节并在注释里写明原因。

**实际验证**（真实模型，只走 recheck 通道不落库；`set PYTHONNOUSERSITE=1`）：

| 样本 | 期望 | 实得 | score | 单条耗时 | 复核 |
|---|---|---|---|---|---|
| 磨皮术的效果可能不是永久性的 | 非硬违规 | 合规 | 2 | 9.7s | 3.6s，dismiss 留痕 |
| 皮肤愈合后，应更显光滑。 | 非硬违规 | 疑似 | 1 | 8.9s | 3.9s（词表已降级） |
| 可能需要大约三个月才能恢复正常肤色 | 非硬违规 | 疑似 | 1 | 9.4s | 3.3s |
| 保证三个月恢复正常肤色 | **硬违规** | 硬违规 | 0 | 6.5s | 跳过（无信号） |

不符期望 0 条；正反对照成立。`pytest tests -q` → **356 passed in 15.45s**（基线 333）。
改动了 3 条既有断言，理由都是链路真的变了、不是放宽：
`test_d3_contract` 的 calls 计数（multi 8→9）、`test_integration` 的费用与 token 断言
（改为"落库账 = 工具上报账"并钉住"无语境信号必须跳过复核"）、
以及上面那条重复上传用例的字节复用。

**风险 / 遗留（触发 §六.2 停止条件，等你决定）**：
① **单条时延 8.9–9.7s，超过 8s**。复核串行依赖判定，条目内部无法并行；
已做的优化是"有语境信号才复核"，把无信号样本从 ~9s 降到 6.5s，
但有信号样本仍是两次串行调用。可选路线：
 A. **首call就带整篇上下文**——从根上不产生第二次调用，判定与语境一次做完
    （最符合 ≤5s 目标，但改动判定主链路与提示词，覆盖需要重新验收）；
 B. 只把复核用于 hard/被降级命中，soft 不复核（现在就是这个策略，收益已用完）；
 C. 换更快的复核模型或缩短复核 prompt（费用换时延，效果需实测）；
 D. 接受"含糊条目 ~10s、干净条目 ~6.5s"，把批量并发（已实现 4 路）当主要提速手段：
    10 条实测约 3× 提速，可达 ≤30s 目标。
② 单条 9s 也意味着 `Check.vue` 的 5 分钟超时预算仍够用，但用户体感需要"已等待秒数+取消"（T3）。
③ 复核结论目前只影响本次判定，尚未回流成规则候选（T5 第 2、3 点）。

**规则 / 评测**：未改 `rules` 表数据与法条正文；无表结构变更。
判定行为变化：① 全部检测手段的命中都过语境闸；② 否定语境命中降级为疑似（T1 已有）；
③ 有语境信号的条目多一次整篇复核，复核可升回硬命中或驳掉命中（驳掉必留痕）。

## v0.6.1 · 整篇上下文判定（路线A）+ 词表收紧，附一条记录更正

**改动**：① 判定主链路从"逐片段两次串行调用"改为"首 call 带 `sources.full_text` 一次判定"：
`merged_judgment(..., context)` 把整篇作为 `document_context` 交给模型，并把 T1 的否定/假设信号
作为 `negation_hints` **显式写进提示词**（统筹方要求：不做成代码里的静默开关）；引文契约与
N6 三重校验一字未动；有上下文时 N7.6 复核跳过并记 `recheck_skipped=context_in_first_call`。
② 新增 `sources.full_text`（LONGTEXT NULL）+ 幂等迁移 `scripts/migrate_sources_full_text.py`
+ **conftest 钩子同批提交**（上一轮统筹方漏掉钩子导致远端克隆跑不绿，这次一次性带上）。
③ `crud/audit.script()` 内部快照加 `source_id`（不改任何接口响应）；
`AuditTool._source_text` 读库而非重读原始文件——重读海报要再跑 OCR（实测单张 4 秒起），
用更慢换更准方向就错了；无素材来源返回 None，自动退回"有信号才复核"，不做静默降级。
④ 修复真 bug：`downgrade_descriptive_hits` 的模糊限定词分支漏写 `severity_before_gate`
（否定分支有写），导致被词表降级的命中永远走不进复核升回分支。实测 recover 2 条红队样本。
⑤ **判定口径变更（统筹方批准）**：`HEDGE_WORDS` 里的单字"应""一般"不再单独构成降级理由，
必须与 `PROGNOSIS_CONTEXT_WORDS`（愈合/恢复/疗程/术后/个月/消肿/结痂…）同现；同现范围允许在
整条话术内，因为「皮肤愈合后，应更显光滑」的限定词与语境词分属两个分句，只看命中片段会把
正当的常规告知重新判成硬违规——那是把误杀修成漏放的反方向错误。

**实际验证**（同一环境、同一脚本、每条件各 2 遍，16 条红队样本；指标按统筹方要求拆三个）：

| 条件 | 硬违规(0) | 放行(2) | 轴漂移 | TP_axis | 未完成 |
|---|---|---|---|---|---|
| main（T2） | 6 / 6 | 5 / 5 | 3 / 3 | 3 / 3 | 5 / 5 |
| 路线A | 7 / 7 | 5 / 5 | 3 / 3 | 4 / 4 | 4 / 4 |
| 路线A + 收紧 | 8 / 9 | 5 / 4 | 3 / 4 | 5 / 5 | 3 / 3 |

放行数从未超过基线 5（红线未触碰），收紧后第二遍还降到 4。四条正反样本三遍全对：
`磨皮不是永久→1`、`应更显光滑→1`、`大约三个月→1`、`保证三个月→0 硬违规`，不符期望 0 条。
单条 6.7–8.0 秒（目标 ≤8s 达标），耗时大头仍是 retrieve 2.5–3.9s 与 detect 3.7–4.5s。
`set PYTHONNOUSERSITE=1&& pytest tests -q` → **360 passed in 18.30s**。

**记录更正（有据可查，不接受无据更正）**：统筹方审计称"commit1 中没有 severity_before_gate 赋值，
所以实施者上一轮说修复已在 wip 里是错的"。`git show 4925a9f:backend/agents/compliance.py` 实测：
第 70 行（否定语境分支）与第 92 行（模糊限定词分支）**都有该赋值**，且 `effective_hedges` 在该提交出现 0 次；
`d638e7b` 才引入收紧。结论：severity 修复随路线A 落在 commit1，词表收紧在 commit2，
实施者上一轮的陈述成立。另一条审计意见（收紧只到 commit2）属实，已采纳。

**为什么没有拆成三个提交**：审计要求把"severity 修复"单独成一个提交，但该修复与路线A 在同一次
改动中落地（4925a9f 的树里就有）。要拆必须先造一个"主链路已改、severity 仍漏写"的中间提交——
那是制造没发生过的历史，且让 bisect 经过一个已知带 bug 的版本。故按事实拆两个：
`feat(audit) 主链路+修复` 与 `change(rules) 词表收紧`。

**风险 / 遗留**：① `negation_hints` 与 `document_context` 都进 prompt，整篇越长首 call 输入越大，
上限截到 4000 字；长文档的召回尚未做规模测试。② 轴漂移 3 条经查是 `safety_guarantee` 与
`efficacy_claim` 语义重叠（旧结论曾同时命中两轴），属规则设计问题，留给 B 阶段处理，
没有用调提示词糊过去。③ retrieve 2.5–3.9s 优化记入遗留，本轮不做。④ 时延虽达标但接近上限，
F 阶段的取消按钮（D 阶段逻辑）必须同期落地，否则用户体感仍是"卡住"。

**规则 / 评测**：**判定口径变更**——"应""一般"需与预后/周期语境词同现才参与降级（收紧后门已关）。
`rules` 表数据与法条正文本轮未改；表结构新增 `sources.full_text`（LONGTEXT NULL，幂等迁移）。

## B · 轴边界与一条度量更正（含一个真实漏放 bug）

**改动**：① 提示词显式写"一句话可同时命中多轴，各轴按自己的 pattern 独立判断、独立返回命中，
不得为'只归一个轴'丢掉另一轴，也不得把本轴 pattern 未覆盖的违法性算到本轴"；
② `efficacy_claim` / `safety_guarantee` 定义改为归因互斥（前者只管见效速度/改善程度/维持时间，
后者只管风险/副作用/不良反应/并发症/温和无刺激），走**既有** `scripts/seed_rules.py`
版本机制落库，不另写迁移脚本；③ `seed_rules.py` 末尾的行数守卫 `total not in (11,14)`
改成语义不变量"每个轴恰好一条 enabled"；④ 修 `aggregate_claims` 一个真实漏放 bug。

**必须先说的度量更正**：上一轮报的"3 条轴漂移"是**我的统计脚本量错的**，不是产品的判定问题。
`aggregate_claims` 把同句多轴聚合成一条 claim，`claim['axis']` 只是首条命中的轴、
`claim['axes']`/`claim['evidence']` 才是全集；我的 A/B 脚本读的是 `axis`，于是把
"两轴聚合成一条显示"读成"第二轴漏判"。产品侧 `JudgeAgent` 一直读 `axes` 全集，是对的。
用修正口径把同一批样本重跑，v0.6.1 规则（v2 重叠定义）与新规则（v4 互斥定义）**都是 drift=0**：
所以规则互斥没买来任何召回/精度提升，它的价值只在归因正确（旧定义里 efficacy_claim 写着
"效果**或安全性**"，商家和运营看到的轴标签会把安全性违规标成效力问题）。
上一轮"两轴语义重叠"的定性有一半成立（定义确实重叠），但支撑它的数字是错的，此处一并更正。

**顺带查出的真 bug（漏放）**：`aggregate_claims` 用首条命中复制出 claim，把首条的
`downgraded=True` 也复制成了整句属性。于是一句里"首条是被降级的疗效提示 + 后跟真实硬违规"时，
`_score` 会把整句当"仅提示"跳过 → 分数 0 变 1，**且结论取决于模型返回命中顺序**。
现改为：只有本句每条证据都被降级时才算降级。测试同时钉两种返回顺序。

**v3 写法实测失败并已修正**：第一版互斥措辞写成"…不在本轴计"，模型把纯安全性句子
（"绝对安全，零风险，没有任何副作用"）折进 efficacy_claim 的唯一命中、safety_guarantee 返回空
——是**漏判**而不是重复计分。v4 改成"本轴不得替另一轴下结论 / 本轴仍须独立返回命中"，
只限定归因范围，不否定命中资格。两版都在版本链里（v3 的教训记进 `rules.json` notes）。

**实际验证**：

| 条件（口径均已修正） | 硬违规 | 放行 | 漂移 | TP_axis | 两轴并存 |
|---|---|---|---|---|---|
| v2 重叠定义 | 8 / 8 | 5 / 5 | 0 / 0 | 8 / 8 | 3 / 3 |
| v4 互斥定义 + 本次修复 | 8 / 9 | 5 / 4 | 0 / 0 | 8 / 9 | 3 / 3 |

`#70 #71 #72` 三条 6/6 次都同时命中两轴（验收达成）；放行数从未超过基线 5；
四条正反样本 0 条不符期望（`磨皮不是永久→1`、`应更显光滑→1`、`大约三个月→1`、`保证三个月→0`）；
单条 6.6–7.4 秒。没有加任何去重规则（同句多轴仅计一处是 `_score` 原有语义，测试钉住）。
规则版本链：`efficacy_claim v1(off) v2(off) v3(off) v4(ON)`、`safety_guarantee` 同构，
旧行只翻 `enabled` 标志、不删不改；`seed_rules.py --apply` 复跑 `inserted=0 skipped=11`，幂等。
表结构本轮未改：`SHOW CREATE TABLE rules` 逐列一致，只有 `AUTO_INCREMENT` 从 22 涨到 24
——那是插入新行带来的自增计数器，不是结构变更，不拿"前后一致"含糊过去。
`set PYTHONNOUSERSITE=1&& pytest tests -q` → **363 passed in 29.66s**（新增 3 条并存/严重度测试）。

**风险 / 遗留**：① 守卫改动放宽了一个写死数字、换成语义检查——它原本会**挡住任何一次规则编辑**
（包括 G 阶段运营改规则界面），不改就落不了地，此处按"守真不变量"重写并同步改了测它的测试；
② `#70`（"挺温和的，正常护理基本没事"）主轴仍常归 efficacy_claim：模型把"基本没事"当模糊限定，
但"基本"不在 `HEDGE_WORDS`，所以分级闸无法降级、维持 hard。**要不要把"基本"收进词表请统筹方定**，
我没有擅自加——刚收紧过"应/一般"的后门，再随手放一个高频词进去是反方向操作；
③ 前端 HitCard 目前显示的是 `hit.axis` 单值，商家看到的轴标签不全，F 阶段重设计时改用 `axes` 全集；
④ 两轴并存的收益只在归因，不在指标，若统筹方认为不值得动规则数据，回退方式是
`seed_rules` 把 v2 重新置 enabled（历史行都在）。

**规则 / 评测**：`rules` 表数据版本 +2（v3→v4，两轴定义互斥化，旧版保留）；
`EVAL.md` 新增 §2.1「轴命中怎么读」——统计必须读 `axes`/`evidence`，不得读 `axis` 主轴。

## C · 分段锚点绝对偏移（含一次 parse 层目录重构）

**改动**：① `Piece` 增加 `start/end/spans`，切分时**按块**就地算出绝对字符区间（忽略空白差异，
所以剥过行首序号、压过换行的话术仍然指得回原文），`spans` 给这句话在整篇里的**全部**出现位置；
② `scripts` 新增 `source_start` / `source_end`（INT NULL）并入库，预览与提交**都**返回锚点
（`items_detail` 另带 `source_occurrences` 与 `script_id`）；③ 前端渲染改为按区间高亮，
模糊定位退成兜底路径，服务端锚不上与前端搜不到分开显示（后者仍显示"位置未知"，不许猜位置）；
④ 目录重构：`backend/parse/` 拆成 `base.py`（契约+注册表+能力探测+编解码，307→240 行）、
`split.py`（切分与锚定）、`parsers/{documents,media}.py`——加第 4 个真实文件会破"每目录 ≤3 个"，
按约束写明的方向用子包，而不是把注释删了凑行数。

**为什么锚点必须在解析层算**：只有 `split_doc` 知道每条 piece 属于哪个块。放到 tools 层整篇模糊搜，
同块内两句相同文案会一起指到第一处——那正是"点第 5 条滚到第 1 条"的成因；而且逐条重扫长文
是 O(n²)，200 条 × 20 万字符会把预览从毫秒级拖成秒级（这洞我在写成 tools 层时发现并改掉了）。

**去重与"分别高亮"的关系**：`dedupe_limit` 按文本去重，同一句写两遍只入库**一条**话术
（省掉一次重复审查与重复计费）。改它等于改入库条数与批量成本，不由这一层决定，所以锚点给出
`spans` 全集，让界面两处都亮、记录仍是一条。

**实际验证**：
- `set PYTHONNOUSERSITE=1&& python -m pytest tests -q` → **372 passed in 16.48s**（新增 9 条：
  锚点单测 7 + 预览/提交 e2e 1 + 截断越界报"未知" 1）。
- 库内真实素材重解析：8 份 / 41 条话术，**锚点覆盖率 41/41 = 100%**，偏移切回原文与话术
  不一致 **0 条**。
- 库里没有的形态另造真文件补测（不拿挑过的样例充数）：docx 2/2、xlsx 3/3、pptx 2/2（含备注）、
  **OCR 海报 2/2**、重复句 2/2 且 `spans=2`（两处都给出来），偏移错 0。
- `cd frontend && npm run build` → **✓ built in 6.32s**，无类型错误。
- 迁移：`python -m scripts.migrate_script_anchors` 预览两列 → `--apply --show` 执行 → 复跑"跳过"。
  `SHOW CREATE TABLE scripts` 前后逐列对比只多 `source_start`/`source_end` 两列，
  `AUTO_INCREMENT` 保持 182 未变（没有删行、没有动数据）。
- e2e 里我一度把期望偏移写成手数出来的 `11+len(line)`（错），改成从原文 `whole.index(middle)`
  独立推导；`.txt` 上传走默认 `mode=blank`，单换行不切开，测试数据改成空行分段而不是迁就实现。

**风险 / 遗留**：① 手工录入（非素材）的 `scripts` 两列恒为 NULL，前端仍走模糊定位兜底——
这是既有数据的现实，不是新功能；② 超过 `FULL_TEXT_STORE_LIMIT`（20 万字符）的素材，
越界锚点按规则置 NULL，界面上会显示"位置未知"而不是错位置；③ 浏览器里的实际高亮效果
（点击结果自动滚动、两处同时亮）我没有真机点过，需要你在 1280 宽度下确认一次；
④ `backend/parse/__init__.py` 的门面 re-export 是这次唯一的路径变化，外部调用方
（含 RUNBOOK 里的 `from backend.parse import capabilities`）全部不受影响，
4 处测试里 `import backend.parse.media` 改成了 `backend.parse.parsers.media`
（monkeypatch 的目标模块必须是被调用的那一个，指错对象会静默失效）。

**规则 / 评测**：`rules` 表数据与词表本轮未改；判定链路未改；表结构变更见 `db_schema.md` 变更记录。

## T-A · doc_lint：把"文档写着支持、跑起来不行"变成机器可查的红灯

**新增** `scripts/doc_lint.py`（只读，不改任何文件；红灯时退出码 1）四类检查：
① 文档里写的代码路径必须真实存在；② 文档里的数量声明必须等于代码事实
（事实基线由源码现数：`mcp_tools=8`、`agents=5`、`axes=11`、`detectors=3`、`dev_agents=6`）；
③ 文档声称的技术栈必须在代码里有 import（`langchain`/`langgraph` 现在就是 0 处 → 红灯）；
④ 每目录真实 .py/.vue 数量 ≤3。刻意不 import backend：体检要在装不上依赖的机器上也能跑。

**首轮报出 14 条红灯，修完剩 2 条**（剩下的正是 T-B 要消除的技术栈欠债，不假装它们不存在）：
- 真漂移已改：`api_spec.md` 把鉴权依赖写成 `backend/core/deps.py`（实际在 `security.py`）、
  工具数 6→8；`CLAUDE.md` 目录树写成 `backend/agents/detectors.py`（实际在 `base.py`）、
  已删除的 `api/v1/router/__init__.py`、开发子 Agent **4→6**；
  `skills/doc-parse-engines.md` 的 `backend/parse/media.py` → `parsers/media.py`（我上一段重构留下的）；
  `db_schema.md` 10→11 条轴、`requirements.md` F5 8→11 条轴与 MCP 6→8、`RUNBOOK.md` 6→8；
  `SKILL.md` 的 S5–S9 还挂着 `TODO（D2/D3/D5）` 而实际都已交付 → 按真实状态改为已验证，
  S7 的口径从"LangChain 工具调用（Tool 绑定）"改成"只作模型适配层"，并把 doc_lint 自己登记成 S11。
- **检查器自己的三轮假阳性也已修**（这部分比修文档重要，误报会让人开始忽略红灯）：
  `data/law/*.md` 里的"第五条九项"是法条原文不是数量声明 → 移出扫描范围；
  `3 条轴漂移` 被当成"轴数声明" → 加 `(?!漂移|样本)`；
  `~/.hermes/skills/.../SKILL.md` 是家目录路径 → 路径正则加 `(?<![/~.])`；
  **"删掉 5 处与代码不符的说法：总览图里 6 个工具"是复盘句不是当前声明** → 整行复盘护栏；
  `CHANGELOG` 提到后来被删掉的文件是历史经过 → 历史记录不参与路径漂移检查（改它等于改历史）。
- 测试还抓到工具一个真 bug：`path.relative_to(ROOT)` 对仓库外文件直接 ValueError →
  改为 `_label()` 兜底。

**目录上限做了"登记式豁免"而不是关检查**：`tests/`、`tests/agents/`、`tests/rag/`、`scripts/`
豁免（pytest 惯例是一个被测模块一个测试文件；scripts 是 RUNBOOK 写死的入口路径），
豁免规则写在代码里并写明理由，第四个新目录想豁免必须先补理由。`backend/`、`frontend/src/` 仍严格 ≤3。

**同步落纪律**：`RUNBOOK.md` 演示前清单加入"doc_lint 红灯 0 条 + pytest 全绿 + npm build 通过"；
`CLAUDE.md` §4 组件⑥ 指向 `scripts/doc_lint.py`，并新增 §4.1「术语三分」表
（业务智能体 5 个=真跑的类／开发子 Agent 6 个=文档约定的分工角色、不会自己跑／
MCP 工具 8、规则轴 11、检测器 3=被调用的零件），答辩时不会被"你们到底有几个 Agent"绕倒。

**实际验证**：`set PYTHONNOUSERSITE=1&& pytest tests -q` → **381 passed in 24.95s**（新增 9 条
`tests/test_doc_lint.py`，含"红灯清单必须恰好等于登记欠债"的门禁测试：冒出新的漂移或欠债清单
没同步收窄都会失败）；`python -m scripts.doc_lint` → 红灯 2 条（langchain / langgraph，T-B 处理）；
`npm run build` → ✓ built in 6.28s。

**风险 / 遗留**：① 检查器不理解语义，复盘护栏是词表级的，新写法仍可能漏判或误判，
红灯清单仍需人看一眼——这条局限写在代码注释里；② `scripts/` 有 24 个平铺 .py（含 doc_lint 自身），靠豁免过关，
交付后按主题分目录（迁移要同步改 RUNBOOK 里的调用路径，风险高于收益，故不在本轮做）；
③ langgraph 那条如果本轮不落地，必须改文档口径为"编排为显式实现"，不能留着红灯收工。

## T-B · LangChain 只作模型适配层（含我把 env 依赖搞坏又修回的全过程）

**改动**：① 新增 `backend/model/`：`langchain_model.py`（`LangChainChatModel`，与
`UrllibChatModel` 同签名同返回结构）+ `__init__.py` 的 `make_chat_model()` 按
`LLM_BACKEND=urllib|langchain` 选择，**默认 urllib**（已实测全绿的那条路，切换要显式、要能一键回退）；
② 两个组合根改走选择器：`audit_tool.AuditTool.__init__` 与
`services.compliance.redteam_operations`（原来是写死 `UrllibChatModel(...)`，
那样"换了后端"只会在组合根之外偷偷发生）；③ `model_error` 补 OpenAI/LangChain SDK 的异常分类
（`status_code` 走 http、`APITimeoutError` 走 timeout），**保持与 urllib 相同的重试语义**
（4xx 不重试、5xx 重试两次）——不补就会变成"任何错误重试三次"，两后端不等价；
④ `requirements.txt` 加 `langchain-core==1.7.0` / `langchain-openai==1.7.2`，`.env.example` 加 `LLM_BACKEND`。

**判定链路一个字没动**：DETECTORS 注册表、线程池、分级闸、三重校验、算分落库全是原样。
LangChain 只承担"这一次 chat 调用交给谁"，所以文档口径写清**LangGraph 未接入代码**
（编排是显式实现），不为了"用了编排框架"去重写 N1→N10。

**我把环境搞坏又修回的过程（必须留痕）**：第一轮我用 `--ignore-installed` 装
`langchain-core<0.4`，而这台机器 env 里**本来就装了 langchain 1.4.7 / langgraph 1.2.16 全家桶**，
于是 core 被我降级，`pip check` 一片"1.x 需要 >=1.6.13 却是 0.3.86"。
修复：`--dry-run` 先看清只会动哪两个包 → 装 `langchain-core>=1.6.13,<2`（pip 挑了 1.6.12，
仍差 0.0.1，再钉 `langchain-core==1.7.6`，pip 元数据最终 1.7.0；包内 `__version__` 常量写 1.7.6，
上游自身对不上，这里以 `pip show` 为准）→ `pip check` 的 langchain/langgraph 冲突归零。
加载来源全程验证在 `E:\Anaconda_download\envs\py312_env`，没有落到 C 盘 user-site。

**第一个真机验收直接失败，暴露一个测试盲区**：注入假客户端的 10 条测试全绿，
真跑却 5 条全部 `score=-1`、每次调用 7–9ms、tokens 0/0。探针打出原始异常：
`ValidationError: Found timeout supplied twice`——我把 `timeout` 同时传给
`ChatOpenAI(timeout=...)` 和 `model_kwargs={'timeout':...}`，客户端构造即失败，
而"能不能构造"这件事 fake client 永远测不到。修完后补了 **真构造 ChatOpenAI（不联网）** 的回归测试；
顺带发现 `extra_body` 必须单传（混进 model_kwargs 时 pytest 已给出去重警告），
以及真实字段名是 `request_timeout`（`timeout=` 只是别名，`client.timeout` 这个属性不存在）——
我第一版断言就是照着猜的属性名写的，跑挂之后才去查字段表。

**实际验证**：
- 两后端各跑 5 条正反样本（含两轴并存那句）：**5/5 完全一致**（分数、命中轴、严重度、引文），
  且每条的 `prompt_tokens` 逐条相同（17535 / 16887 / 19064 / 17387 / 17463）——
  说明交给模型的载荷没变，变的只是传输层；`completion_tokens` 有几枚差异属生成抖动。
  总耗时 urllib 42.6s vs langchain 23.6s（同批 5 条），langchain 反而更快，不作为结论、只作记录。
- `set PYTHONNOUSERSITE=1&& pytest tests -q` → **396 passed in 19.24s**（新增 12 条后端契约测试：
  返回体逐字段同构、错误分类与重试语义等价、用量缺失不记 0、分段内容拼接、密钥与提示词不外泄、
  真构造客户端、未知后端名直接报错）。
- `python -m scripts.doc_lint` → **红灯 0 条**：T-A 留下的 langchain/langgraph 两条技术栈红灯，
  一条靠真实 import 消除，一条靠把说法改诚实（"已安装、未接入"）消除——**没有为了让灯灭而实现 langgraph**。
- `cd frontend && npm run build` → ✓ built in 5.77s。

**风险 / 遗留**：① 默认后端仍是 urllib，langchain 只做过 5 条样本的一致性验证，
不是全量回归过的默认路径；要切成默认得再跑一整轮红队与锚点集，本轮不做；
② `LangChainChatModel` 只覆盖 `complete()`，红队的 `reasoning_content` 采集依赖 SDK 的字段位置，
真机日志里我未逐条核对思考链长度（urllib 路径已核对过）；
③ `pip` 元数据 1.7.0 与包内 `__version__` 1.7.6 不一致，若上游修复，版本号要同步改
`requirements.txt` 与 CLAUDE.md §9；④ langgraph 仍是"已安装、未接入"，
如果老师追问"为什么不用"，答案在 CLAUDE.md §2 那一行，不要临场编。

**规则 / 评测**：`rules` 表数据、词表、判定口径本轮均未改；评测样本不变，只增了后端一致性核对。

## T-C · MCP 真实协议调用：一半达成，一半按预案停下（不假装）

**做了什么**：① 新增 `backend/mcp_server/client.py`：`StdioServerParameters` + `ClientSession`
真实起子进程走 stdio，`MCPClient` 一个进程一条 session（专用线程跑事件循环、
调用线程 `run_coroutine_threadsafe` 投递、锁串行化）；Windows 两个坑按统筹方提醒钉死——
显式传 `sys.executable`（不写 `python`，否则命中 C 盘全局解释器）与子进程 env
`PYTHONNOUSERSITE=1`（否则读到 C 盘 user-site 副本包）。
② 开关 `MCP_MODE=inline|client`，默认 inline；业务侧唯一接缝 `_cached_law_lookup` 按开关分流。
③ `--selftest-mcp`：真起子进程、经协议调用一次工具并**断言返回**。
④ `decode()` 优先取 `structuredContent`，只在缺失时解析文本——两处各解一遍迟早出现
"文本与结构不一致"的分裂结果。
⑤ 放在 `mcp_server/` 而不是 `agents/mcp_client.py`：`agents/` 已有 base/compliance/redteam
三个真实文件，加第四个就破"每目录 ≤3"；协议客户端本来就属于 MCP 侧。目录树同步改实话。

**已经过硬的证据**（原样贴）：
```
{"transport":"stdio","tools":8,"called":"db_query_rules","rows":1,
 "first":{"axis":"absolute_terms","level":"hard","detector":"regex","version":1},
 "assertion":"PASS"}
```
子进程日志同时可见 `ListToolsRequest` 与 `CallToolRequest`，说明这条确实走了协议而不是内链。

**没做到的部分（停止条件 2 的预案，用了约 1.5 小时）**：
`MCP_MODE=client` 下跑真实审查，**第一次 `rag_search_law` 永远不返回**，撞穿超时；
第二次起同一工具 7.2s 正常。三组对照事实：
- 同一 session 里第一次调用 `db_query_rules` → 0.5s OK，所以"首条请求"本身没问题；
- 同一套检索在**独立进程**里：`import backend.rag.retrieve` 1.3s + 首次 search 5.4s = 6.7s；
- 关掉 chromadb 匿名遥测（`ANONYMIZED_TELEMETRY=False`）不改变；我们代码里 0 处 `tiktoken`。
判定链路本身没有因此出错：第一条按 `score=-1 未完成` 结案，**没有被当成合规放行**（铁律成立）。

**两次误判都已公开收回**（不是私下改掉）：
① 我先判"jieba 把 `Building prefix dict...` 打到 stdout 冲掉了 JSON-RPC 响应"——
隔离探针实测 stdout 0 字节、那些噪声走 stderr，**判断错了**；`warm_libraries()` 只保留为
降噪 + 提前加载，注释里写明它不是这条超时的修复。
② 我写的护栏测试一开始断言方向是反的（断言"污染存在"），且去掉预热的对照组证明它抓不到东西
——即**空跑**；改为"先证明捕获机制有效（故意打印必须被抓到），再要求真实路径 stdout 为空"，
11 条测试全绿且有对照组支撑。

**验收口径按预案调整**：`requirements.md:54` 改为"8 个工具按 MCP 契约注册，可被外部客户端经
stdio 真实调用（`--selftest-mcp` 断言返回）；业务内链默认复用同一实现以减少序列化"，
`.env.example` 里把 client 模式的实测边界与这条未解挂起写清楚，并明确"演示时不要打开"。

**实际验证**：`tests/mcp/test_client.py` 新增 11 条离线测试（协议语义部分不依赖子进程：
`decode()` 四种输入、`server_params()` 钉解释器与 user-site、构造客户端零副作用、
inline 模式拒绝协议调用、位置参数按 inputSchema 顺序映射、未注册工具名在发出前就拒）；
`set PYTHONNOUSERSITE=1&& python -m pytest tests -q`、`python -m scripts.doc_lint`、
`npm run build` 结果见提交信息。

**风险 / 遗留**：① **未解**：子进程首次触达 Chroma 的调用挂到超时，后续正常。留给下一轮的
排查入口已列（不重复我已排除的三条）；如果评审要现场演示 MCP，用 `--selftest-mcp`，
不要用 `MCP_MODE=client` 跑审查；② client 模式没有全量回归过，只是"能握手、能列、能调通
非检索工具"的程度；③ `warm_libraries()` 若在别的机器上让握手变慢，直接删掉它没有功能损失
（它只降噪）。

## D · 改写与批量检查的硬超时、可取消、已耗时

**改动**：① 模型适配器新增**整次请求预算**：`UrllibChatModel` 在每次尝试前检查剩余预算，
并把剩余时间**压进这一次的网络读超时**（`self.attempt_timeout`），预算见底就抛
`deadline_exceeded`；② `AuditTool.rewrite_audit(audit_id, budget_seconds=...)` 把预算发给
**所有会打模型的持有者**（tool / rewriter / auditor 三个位置，不是只设 `self.model`），
用 `finally` 归还，避免预算漏给下一个请求；超时映射成 `DeadlineExceededError`（HTTP 504，
`code` 与状态码一致，沿用既有约定）；③ 接口读取 `REWRITE_TIMEOUT`（默认 90 秒）；
④ 前端 `http.ts` 支持 `AbortSignal`，并把"用户取消"与"请求失败"分成两条路
（`CanceledError` / `isCanceled`，取消不弹红条、不动登录态）；批量检查与"采纳改写建议"
都装了停止按钮 + 已耗时秒数显示；⑤ 前端超时 120s > 后端 90s，让后端的有意义错误先到。

**关于"十分钟假死"的诊断，只写我能证实的部分**：
算术来自代码本身——改写一次 = 1 次生成调用 + 每稿一次完整重审（重审内部还有 detect 与
可能的整篇复核），每一次调用最坏是 `3 次重试 × JUDGE_TIMEOUT=180s`，
按默认 2 稿上限就是 `3×180×(1+2×k)` 量级，早已越过任何合理等待时间；
`JUDGE_TIMEOUT` 只管**单次阻塞读**，从来没有覆盖过"整次请求"，这就是假死的结构性原因。
但**那一次具体现场我无法复现**（发生在上下文压缩之前，`timings_ms` 明细没留下来），
所以这里不声称"我复现并定位了那次故障"，只说清了同类故障的成因，并且新上限让它不再可能：
现在无论重试几轮，整次改写最坏 90 秒 + 一次已压缩的读超时，到点就明确 504。

**取消的语义写实话**：后端是同步任务、没有服务端取消钩子，`abort()` 只是前端不再等结果，
那一次请求在后端仍会跑完。所以界面写"停止等待"而不是"已终止"，
并明确"已入库的话术仍在「我的档案」里"——按钮名字叫错会让人以为数据被删了。

**实际验证**：`set PYTHONNOUSERSITE=1&& python -m pytest tests -q` → **414 passed in 23.79s**
（新增 7 条 `tests/test_rewrite_timeout.py`：预算到了不再发请求、单次读超时被剩余预算压小、
超时映射 504、超时不写库（无半成品）、成功与失败两条路径都归还预算、
rewriter/auditor 独立实例也各自收到预算、langchain 后端同一条保护）；
既有 `tests/agents/test_integration.py` 的打桩同步加上 `budget_seconds` 形参，
并断言接口确实把默认 90 秒传到了服务层（否则路由改了、测试还绿，测的就不是真实调用路径）。
`python -m scripts.doc_lint` → **红灯 0 条**；`cd frontend && npm run build` →
**✓ built in 5.85s**（vue-tsc 无错误）。
过程中我自己写坏并被构建抓出来的两处：`requestCancellable` 声明 `async` 却返回普通对象
（TS1064），而且它**根本没被使用**——计时逻辑我在两个组件里手写了，所以这个包装函数是死代码，
直接删掉而不是修好留着；模板里多出一个孤立 `</el-button>`（同样是写完立刻被 vue-tsc 拦下）。

**风险 / 遗留**：① `LangChainChatModel` 只做到"每次尝试前检查预算"，没有把剩余时间压进
它的单次超时（客户端在构造时固定 timeout）——默认后端是 urllib，这条差异记在遗留里；
② 单条审查 `/audit/run` 与批量 `/audit/batch` 仍只有前端超时，没有服务端整次预算
（批量的总耗时随条数线性变化，硬编码上限会误伤大批量，需要统筹方定策略）；
③ 取消后后端那一次继续跑完并照常计费落库，这是事实而非 bug，但如果以后要做"真取消"，
得引入任务表 + 轮询/取消接口，不是前端能单独解决的。

## E · 商家三段状态持久化（材料 → 分段 → 结论）

**改动**：新增 `frontend/src/stores/checkDraft.ts`（Pinia + sessionStorage），
检查页 `onMounted` 按 `client_id` 自动恢复、状态一变即落盘、并给显式"清空本次草稿"出口。

**三条不能假装的设计约束**：
1. **File 对象存不进 sessionStorage**。所以"材料"这一栏持久化的是文件名/大小/已入库的
   `source_id`，恢复时界面直接说"分段与结论都在，原始文件需重新选择才能再传一次，
   库里数据不受影响"。偷偷丢掉文件而不告诉用户，会被理解成"我上次上传白做了"。
2. **按 client_id 分键**（`cg-check-draft.<clientId>`），并在读取时校验
   `shape.clientId === clientId` 与 `shape === SHAPE_VERSION`：结构变了或归属不对直接丢弃。
   拿旧 schema 或另一家机构的数据来渲染，比丢一次草稿危险得多——租户隔离在草稿层
   也必须是真的，不能只在数据库 `data_scope` 那一层是真的。
3. **配额写满必须告知**：`sessionStorage.setItem` 抛错（超配额 / 隐私模式禁用）时，
   清掉旧草稿并把 `savedAt` 置空——不能让用户界面显示"已保存"而实际什么都没留下。

**只清显式动作**：`clear()` 只由"清空本次草稿"按钮触发，页面卸载绝不自动删；
同时明确提示"已入库的话术与审查记录不受影响"，把草稿和业务数据的边界说清楚，
否则用户不敢点这个按钮。

**顺带修掉一个类型漂移的隐患**：我最初在 store 里另抄了一份 `DraftPiece`
（字段与接口契约的 `ImportPiece` 几乎同形），被 vue-tsc 当场抓出
`source_start` 可选性不一致——这正是"两处各写一遍、迟早分家"的第一现场。
改为直接复用 `ImportPiece`，锚点字段以后随契约一起走，不需要我在两个文件里同步。

**实际验证**：`cd frontend && npm run build` → **✓ built in 6.14s**（vue-tsc 无类型错误；
第一次构建有 2 个真实类型错，均已修：恢复出的 group 缺 `confidence/warnings/error/chunks`，
草稿 pieces 与接口类型不同形）。`python -m scripts.doc_lint` → 红灯 0 条。
**没有前端单元测试**：项目里本来就没有测试运行器（`package.json.scripts` 只有
dev/build/preview），本轮不擅自引入 vitest 扩范围；恢复流程需要你在浏览器里真点一次
（传文件 → 出结论 → F5 → 看是否回到结论页且提示"已恢复"）。

**风险 / 遗留**：① 草稿只在**同一浏览器标签会话**内有效（sessionStorage 关闭页签即清），
要跨会话续用得换 localStorage + 过期策略，本轮按任务书写的 sessionStorage 执行；
② 恢复的分组 `chunks` 为空，所以结论区的数据来自 `results` 列表而不是重新审查——
如果以后要在恢复态上继续"采纳改写"，得先按 `script_id` 把 audit 记录取回来；
③ 无 FE 测试设施这条与 F 阶段一起暴露：商家端重设计做完后，
高亮/滚动/取消这类交互全靠手工回归，成本会越来越高，建议 D8 前补 vitest。

## 环境卫生 · jieba 词典缓存挪出 C 盘（并证伪了我自己的一条因果推测）

**发现**：`jieba` 默认把词典缓存写到 `C:\Users\<user>\AppData\Local\Temp\jieba.cache`。
两个后果：① 违反"C 盘不装不写"的硬规矩；② 并发首启时进程会读到对方写了一半的缓存，
jieba **不报错而是回退到全量建词典**，内存紧张时直接 `MemoryError`。

**证据**：全量 pytest 里"子进程 stdout 必须干净"那条测试偶发失败，单跑必过；
抓到的失败正文就是 `gen_pfdict → lfreq[word] = freq → MemoryError`。
全量套件时父进程正占着 chromadb/onnxruntime，子进程再全量建词典就撑不住。

**修法**：`backend/rag/embedding.py` 新增 `pin_jieba_cache()`，把 `jieba.dt.tmp_dir`
指向 `data/jieba_cache/`（进 `.gitignore`，可重建、不入库），并静音进度打印；
`retrieve.py` 在 `add_word` 之前调用（否则第一个 `add_word` 就按默认路径建缓存），
MCP server 的 `warm_libraries()` 也调用，预热失败只警告、不拦 server 启动。

**必须写下的证伪**：我原本推测这也是"MCP client 模式第一条 `rag_search_law` 永不返回"的根因，
**修完重测协议探针，第一条仍然 90 秒超时、第二条 7.3 秒正常**——推测不成立。
此前已排除的还有 stdout 污染（jieba 实测走 stderr）与 chromadb 匿名遥测（已关仍复现）。
这条挂起继续留在 T-C 的未解清单里，我不再猜第四个原因。

**验证**：`set PYTHONNOUSERSITE=1&& python -m pytest tests -q` → **419 passed**（含之前偶发失败
那条，连跑两次均绿）；协议探针 `db_query_rules` 经协议 0.4s OK、
`rag_search_law` 首条 FAIL / 次条 7.3s OK，原样记录不粉饰。

## F · 商家端第二套视觉系统（象牙白 + 细金 + 陶土）与结论级反馈

**结构**：新增 `layout/MerchantShell.vue`（顶部横向栏：品牌｜功能区导航｜右上角登录或头像）、
`views/public/Landing.vue`（公开首页，`/` 不再是登录页）、
`views/merchant/Archive.vue`（我的档案：递过的材料 / 查过的话术 / 今日概览三个标签）；
删除 `views/merchant/Portal.vue`（内容并入档案页）。路由改成三线：`/` 公开、`/m/*` 商家、
其余走运营端 `MainLayout`；旧 `/merchant/*` 全量重定向，`/merchant/reviews` 也指向档案页——
**"待复核"从商家端整块消失**（后端接口与运营队列保留，不是 disable 给他看）。
`MainLayout` 删掉 `MERCHANT_MENUS` 与 `isMerchant` 分支，从此只服务平台端。

**第二套令牌**：`styles/merchant-tokens.css`，变量只挂在 `.merchant-shell` 子树。
象牙白 `#FBF7EF`（不是纯白，盯几分钟不刺眼）、哑金 `#B4884B` **只用于线/字/选中态**
（大面积铺金就成营销页）、深棕正文 `#3B2A1D`、陶土红硬违规 `#A8402F`（比朱红暖一档，
语义仍与运营端一族对应，同一条命中两端不会读成两种颜色）；圆角只留 2/4/6 三档；
动效只用在状态确认与位置移动（120/320ms）——审查要等 6–8 秒，入场动画只会放大焦虑；
阴影只允许一层。

**换色不写条件样式**：商家端复用运营端组件（EP 表格、HitCard、SourceText），
它们读通用 `--cg-*`。做法是在 `.merchant-shell` 里加一层**变量映射**
（`--cg-hard: var(--cg-m-hard)` … 连 `--el-*` 一起指过去），组件本身零改动、零 `v-if`。
**刻意不映射间距 `--cg-s-*`**：两套尺度不同，硬映射会让复用组件内外边距错位，
而那种错位只有肉眼能发现——配色可以换皮肤，几何不行。

**交互**：删掉结果行的"定位原文"按钮（点命中即 `scrollIntoView` 自动滚动 + 高亮，
溯源降级成纯文本），命中卡仍保留四件事；👍/👎 挂在**整条结论**上而不是每个命中卡——
存储是 `audits.feedback`，挂到命中会给出"我能逐条推翻"的假暗示；
未选时写"不选也不影响判定"，写入后写"已记录，可改"，**存不上就显示没存上**。

**设计说明**按统筹方要求写进 `frontend/README.md` 新增章节「一之二、商家端是第二套系统」：
为什么两套 shell、每个颜色/圆角/动效决定的理由、为什么不映射间距、为什么首页不是登录页、
删掉的那一步为什么该删。

**被工具当场挡下的我自己的错**（都改了，没有悄悄绕过）：
① `Archive.vue` 写了契约里不存在的 `report.suspect` → 改用真实四项；
② 头像想用 `user.client_name`，`User` 类型没有该字段 → 改为可核对的 `机构 #<id>`，不编名字；
③ Vue 插值写成 Ruby 的 `#{ }`；④ `--cg-line` 是**边框简写**，我写成 `1px solid var(--cg-line)`
会展开成非法 CSS；⑤ 同一模块拆了两行 import。①②③由 vue-tsc 挡下，④⑤是自己复查时发现。

**验证**：`cd frontend && npm run build` → **✓ built in 5.86s**（vue-tsc 无类型错误）；
`pytest tests -q` → **419 passed**；`doc_lint` → **红灯 0 条**。

**风险 / 遗留**：① **1280 不破版我只做了断点与栅格约束，没有真机逐页看过**，
需要你在 1280 宽度确认：首页 / 登录 / 文案审核三阶段 / 档案三标签 / 反馈按钮 / 停止等待；
② 商家端仍复用运营端表格（靠令牌映射换肤），若以后要商家自己的表格语言，应新写组件
而不是继续堆映射；③ "今日概览"读 `dailyReport` 失败时静默不显示数字（宁可没数字也不给假数字），
但没有重试入口；④ 前端仍无测试运行器，这套视觉的可回归性全靠人工，D8 前建议补 vitest。
