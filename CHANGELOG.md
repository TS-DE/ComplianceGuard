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

**遗留问题**
- （C/D/E 完成后补）

**规则 / 评测集变动**
- 无（rules 表为空；锚点集尚未入 Chroma）
