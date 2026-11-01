# CHANGELOG

> 状态：生效 ｜ 最后更新：2026-11-01 ｜ 维护：Claude
>
> 每条四段式：做了什么 / 验证证据（命令 + 实际输出）/ 遗留问题 / 规则或评测集变动。
> **验证证据只写真实跑出来的输出，不写"已完成"。**

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
