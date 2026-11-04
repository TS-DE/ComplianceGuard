# api_spec.md — 接口契约（分段生长）

> **状态：草案（仅 auth + crud 生效，其余待补）** ｜ 最后更新：2026-11-01 ｜ 维护：统筹方 + Claude
>
> **规则**：每实现完一个模块，才把该模块的接口补进来。**不要在开工前把 30 个接口全编一遍**——
> 那会写出一堆和代码不一致的假契约。接口以代码为准，本文档负责"先定形状"。

---

## 1. 通用约定（全接口适用）

### 1.1 统一返回体
```json
{ "code": 200, "msg": "ok", "data": {}, "total": null }
```
| code | 含义 |
|---|---|
| 200 | 成功 |
| 400 | 参数错误（Pydantic 校验失败） |
| 401 | 未认证 / token 失效 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 409 | 冲突（用户名已存在等） |
| 422 | 业务校验失败 |
| 500 | 服务异常（不泄露堆栈） |

### 1.2 鉴权
- 登录后返回 `access_token`（JWT，HS256，默认 24h）
- 除 `POST /auth/register`、`POST /auth/login`、`GET /health` 外，**全部接口**要求头：
  `Authorization: Bearer <token>`
- 依赖：`backend/core/deps.py :: get_current_user`

### 1.3 分页
- 请求：`?page=1&page_size=20`（page_size ≤ 100）
- 返回：`data` 为列表，`total` 为总条数

### 1.4 时间格式
- 统一 ISO8601 字符串 `2026-11-01T16:00:00`

---

## 2. 鉴权 `/api/v1/auth`（D1 实现）

| 方法 | 路径 | 入参 | 返回 data |
|---|---|---|---|
| POST | `/auth/register` | `{username, password, role?}` | `{id, username, role}` |
| POST | `/auth/login` | `{username, password}` | `{access_token, token_type:"bearer", user:{id,username,role}}` |
| GET | `/auth/me` | — (需 token) | `{id, username, role, created_at}` |

**约束**：密码 ≥ 6 位；用户名唯一（重复 → 409）；密码只存 bcrypt 哈希。

---

## 3. 业务 CRUD（D1 实现，4 套同一形状）

> 四套资源：`clients`(机构) / `scripts`(话术) / `audits`(审查记录) / `rules`(规则)
> 全部遵循下表的**统一形状**，只换路径与字段。

| 方法 | 路径 | 说明 | 特殊参数 |
|---|---|---|---|
| GET | `/api/v1/{res}` | 列表（分页） | `page` `page_size`；`scripts` 与 `audits` 额外支持 `client_id` |
| GET | `/api/v1/{res}/{id}` | 详情 | 不存在 → 404 |
| POST | `/api/v1/{res}` | 新增 | body 为对应 schema |
| PUT | `/api/v1/{res}/{id}` | 修改（部分字段） | |
| DELETE | `/api/v1/{res}/{id}` | 删除 | 有下游引用 → 409 |

### 3.1 各资源字段（与 `db_schema.md` 对齐）

**clients**：`{id, name, industry, contact, plan, created_at}`
- 必填：`name`

**scripts**：`{id, client_id, scene, content, status, created_at}`
- 必填：`client_id, content`；`status` 缺省 `pending`

**audits**：`{id, script_id, score, hit_count, hits_json, law_refs_json, rewritten_text, rewrite_passed, model, prompt_tokens, completion_tokens, cost, latency_ms, incomplete, created_at}`
- **D1 仅做读 + 手工建（调试用）**；写入由 D3 的审查 Agent 负责
- `score` 取值必须是 `2/1/0/-1`

**rules**：`{id, axis, law_article, pattern, level, example_bad, version, enabled}`
- 必填：`axis, law_article, pattern, level`
- `axis` 必须在 `db_schema.md §3` 的 8 个枚举内，否则 422

---

## 4. D3 审查与改写（已实现；D4 待实现）

审查请求：`POST /api/v1/audit/run`，JWT 鉴权，body `{script_id, client_id}`。
返回 `audit_id/score/hit_count/hits/traces/law_refs/incomplete/no_reference/model/prompt_tokens/completion_tokens/cost/latency_ms/disclaimer`。
引文附 `start/end/original_quote`，作废候选保存在 traces；写库时有效及作废痕迹一并进入 hits_json。

改写：`POST /api/v1/audit/{id}/rewrite`，JWT 鉴权，每稿重跑 A1 N1–N8，返回
`rewritten_text/rewrite_passed/recheck/candidates/status`。未完成审查永远不能通过。
成本由配置单价估算；单价未配置则标为零估算，不代表供应商免费。


| 方法 | 路径 | 阶段 | 作用 |
|---|---|---|---|
| POST | `/api/v1/audit/run` | D3 | 提交话术 → 跑 Agent1 → 返回命中与分数 |
| POST | `/api/v1/audit/{id}/rewrite` | D3 | 调 Agent2 生成改写稿并二次审查 |
| POST | `/api/v1/redteam/run` | D4 | 跑一轮红队压测（Agent3→Agent4） |
| GET | `/api/v1/redteam/{run_id}` | D4 | 取压测结果（漏杀清单） |
| GET | `/api/v1/reports/daily` | D4 | 调 Agent5 出日报 |
| GET | `/api/v1/reports/redteam/{run_id}` | D4 | 出压测报告 |

## 5. MCP 工具契约（D2 实现，非 HTTP）

| 工具 | 入参 | 返回 | 服务于 |
|---|---|---|---|
| `rag_search_law` | `query:str, top_k:int=3` | `[{text, code, source, score}]` | Agent1/2/3/4 |
| `db_query_rules` | `axis:str\|None` | `[{axis, law_article, pattern, level, version}]` | Agent1/4 |
| `db_query_violation_history` | `client_id:int, limit:int=5` | `[{script_id, score, hits, created_at}]` | Agent1 |
| `db_query_scenes` | — | `[{scene, sample_scripts}]` | Agent3 |
| `db_save_redteam_result` | `run_id, sample, judge, category` | `{ok:true}` | Agent4 |
| `audit_recheck` | `text:str, client_id:int` | `{score, hits}` | Agent2 |

**验收**：`python -m backend.mcp_server.server --selftest` 打印 6 个工具名。

---

## 变更记录
| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-11-01 | 建立通用约定 + auth + 4 套 CRUD 形状 + 待实现登记 | D1 开工依据 |


## D4 红队与报告
全部JWT鉴权；**其中 `/redteam/run`、`/redteam/{run_id}/gaps`、`/redteam/options`、`/reports/redteam/{run_id}` 为平台级，商家账号一律 403**（`/redteam/options` 的响应含每条轴的 pattern/law_article/detector/version，等于判定规则本身，不能交给被审查方；只在前端藏菜单不算数）。`/reports/daily` 对商家开放但按机构裁剪。
POST /api/v1/redteam/run 请求client_id/scenes/axes/strength=all，一次生成每轴low/mid/high违规样本及control合规对照（默认4轴共16条），顺序调用A1后返回run_id/generated/script_ids。
GET /api/v1/redteam/{run_id}/gaps 返回TP/FN/FP/TN/unjudged矩阵、清单和分轴率。
GET /api/v1/reports/daily?date=YYYY-MM-DD 返回完整/未完成、按轴、按素材形态（`by_source`）、成本和耗时。

`by_source` 的口径：对**已判定**的审查按 `Audit → Script → LEFT JOIN sources.kind` 分桶，
无素材的（手工录入、红队样本）归入 `no_material`。
必须用 LEFT JOIN——inner join 会丢掉无素材的行，让日报看起来"结论全部来自上传文件"。
分桶之和恒等于 `total - incomplete`，这条由测试锁死；商家端仍只统计本机构（与 `by_axis` 同一 criteria）。
GET /api/v1/reports/redteam/{run_id} 返回矩阵、FN/(TP+FN)、FP/(FP+TN)、(TP+TN)/generated及样本量免责声明。
MCP 共 8 个（原 6 个 + `parse_source`、`parse_document`）：db_query_violation_history新增可选run_id；db_save_redteam_result category为TP/FN/FP/TN/unjudged，judge可带script_id精确指定样本，写回scripts.redteam_meta。
全链路费用分judge_cost/rewrite_cost/embedding_cost/total_cost；任一未知total_cost=null，embedding token照常记录。价格及用量仅为估算，不是供应商账单。

## D5-a 话术内容搜索
GET /api/v1/scripts 新增可选 q（最多500字符），按content子串LIKE过滤，与client_id及分页同时生效；%/_按字面转义，不传q或空串保持原行为。

## D5-a2 法条追溯（前端「法条依据」可点开）
GET /api/v1/law/article?code=<命中法条的code>&item_no=<可选，命中项>（JWT 鉴权）

返回：
```json
{"code":200,"msg":"ok","data":{
  "doc":"医疗美容广告执法指南","source":"03_医疗美容广告执法指南.md",
  "code":"医疗美容广告执法指南第5条","article_no":5,
  "item_no":"第五条(五)",
  "item_text":"（五）利用行业协会……作证明的。",
  "article_text":"<该条完整原文，含全部项>"},"total":null}
```
- 传 `item_no` 时返回**该项**原文（命中粒度本来就是"条下的某一项"，只回整条等于让用户自己找）；
  不传时 `item_text` 为 null，只给整条；
- `article_text` 供前端「展开该条全文」使用；
- 只读本地法规归档（`backend/rag/ingest.py::find_law_article`），
  **不查向量库、不调模型**，因此可随时点开且不产生费用；
- 未收录条文 → **404** `{"code":404,"msg":"法规归档中未收录该条文：xxx"}`，禁止编造条文；
- 条文数以归档为准（广告法 74 / 医美指南 10 / 医疗广告管理办法 23 等），
  与入库口径**不同**：入库按 relevance 跳过 procedure，追溯要完整。

## D6 话术批量导入（商家素材是整页文档，不是一条条数据）
POST /api/v1/scripts/import （multipart/form-data，JWT 鉴权）

| 参数 | 说明 |
|---|---|
| `client_id` | 必填，归属机构 |
| `scene` | 可选，场景 |
| `mode` | `blank`(按空行，默认) / `line`(按单换行) / `sentence`(按句末标点，语音与整段连排用) |
| `commit` | `false` 只预览（**不写库也不落盘**）；`true` 入库并保存原始素材 |
| `text` / `file` | 二选一：粘贴文本，或上传文件 |
| `items` | 可选，**JSON 字符串数组**；提供时只入库这些条目（人工剔除误切片段）。服务端只认文本，位置与置信度一律重算 |

支持格式（由 `backend/parse/` 注册表决定，缺失引擎时如实报"未启用"）：

| 类别 | 扩展名 | 引擎 |
|---|---|---|
| 文本 | `.txt` `.md` `.csv` | UTF-8/GB18030 自动识别；csv 一行一块 |
| Office | `.docx` `.xlsx` `.xls` `.pptx` | python-docx（正文真实顺序）/ openpyxl·xlrd（按文件头判格式）/ python-pptx（含备注） |
| PDF | `.pdf` | pdfplumber 文字层；**无文字层的页自动渲染后走 OCR** |
| 图片 | `.png` `.jpg` `.jpeg` `.bmp` `.webp` `.tif` `.tiff` | RapidOCR（onnxruntime，CPU 离线） |
| 音频 | `.wav` `.mp3` `.flac` `.ogg` `.m4a` `.aac` | FunASR SenseVoiceSmall（可选，未装则 422 说明装什么） |
| 明确不做 | `.doc` `.wps` `.ppt` `.odt` `.numbers` `.pages` `.key` | 422 + "请另存为/导出为" 指引 |

**绝不返回 `count=0` 冒充"没有违规"**：解析失败一律 422 并给出原因与下一步动作。

返回（`items` 为兼容既有前端的字符串数组，`items_detail` 是带溯源的新契约）：
```json
{"code":200,"data":{"source":"话术.docx","kind":"docx","engine":"python-docx",
  "confidence":null,"warnings":[],"meta":{"blocks":12},"parse_ms":18,"size_bytes":37012,
  "count":12,"items":["话术1","…"],
  "items_detail":[{"text":"话术1","pos":1,"ref":"第1段","confidence":null}],
  "created":0,"script_ids":[]},"total":null}
```
`commit=true` 额外返回 `source_id`，同机构重复上传同一份内容时返回 `duplicate_of`。

- 强制两段式：先 `commit=false` 预览切分结果，人工确认后再 `commit=true` 入库，
  避免一次传错文件把脏数据写进库、污染后续所有审计统计；
- 切分规则：剥行首序号（`1.` / `（1）` / `一、` / `-`）、去重、过滤 4 字以下噪声、单次上限 200 条；
- **溯源由服务端计算**：客户端传来的页码/置信度一律忽略，勾选项若与文件解析结果对不上则拒绝入库。

## D6-b 素材档案与原始文件回看

| 接口 | 说明 |
|---|---|
| `GET /api/v1/sources/formats` | 能力清单：可扩展名、kind/engine、缺哪个引擎、`modes`、上限。前端 accept 列表必须由此生成，不许手写 |
| `GET /api/v1/sources?page&client_id` | 素材档案分页；商家只见本机构 |
| `GET /api/v1/sources/{id}` | 详情 + `scripts[]`（该素材切出的话术，含 ref/confidence）。**不返回服务器内部路径**，只返回 `file_available` |
| `GET /api/v1/sources/{id}/file` | 原始素材内联返回（`Content-Disposition: inline`）：海报直接显示、录音直接播、PDF 直接翻 |

越权访问他人素材（详情与文件同样处理）返回 **404**，不暴露"这条存在"。
文件路径校验在服务层 `sources.file_path` 统一把门（`is_relative_to` 上传目录），
任何新增入口想读素材都得过同一道闸。

MCP 工具新增两个（共 8 个，`--selftest` 可验）：

| 工具 | 参数 | 用途 |
|---|---|---|
| `parse_source` | `source_id`, `mode` | 智能体按素材 id 取回**当前文件**的逐条话术与溯源，不依赖有人先复制粘贴 |
| `parse_document` | `rel_path`, `mode` | 解析项目 `data/` 内素材；路径锁死在 `data/` 之内，挡 `..` |

## D6-c A1 的第二个入口：按素材预审（不落库）

`POST /api/v1/audit/preview-source` （JSON，JWT 鉴权）

| 参数 | 说明 |
|---|---|
| `source_id` | 必填，已入库素材的 id |
| `client_id` | 可选；**商家账号一律被改写成本机构**，平台账号可指定 |

A1 在这里调 MCP 工具 `parse_source` 自己取内容 —— 商家递来海报、扫描件、录音时，
不需要有人先把上面的字抄进文本框。

```json
{"code":200,"data":{"source_id":12,"filename":"双11海报.png","kind":"image","engine":"rapidocr",
 "count":3,"total_items":3,"truncated":false,"persisted":false,
 "warnings":["识别置信度仅 40%，很可能有误读，请对照原始素材人工核对后再采信结论"],
 "results":[{"text":"保证做完能白三个色度","ref":"OCR块1","confidence":0.93,
             "score":0,"incomplete":false,"hit_count":1,"hits":[…]}],
 "disclaimer":"…不构成法律意见…"},"total":null}
```

三条硬约定：
- **不写 `audits`**：预审是"试一下"，留档要改走 `/scripts/import commit=true` + `/audit/batch`；
- **逐条上限 20**，超出时 `truncated=true` + `total_items`，**不许把"审了 20 条"演成"整份审完"**；
- **单条模型故障只标该条** `score=-1 / incomplete=true`（铁律 5：未完成 ≠ 合规），其余继续。
