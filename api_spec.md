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

## 4. 待实现（D2–D4，只登记，不写细节）

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
