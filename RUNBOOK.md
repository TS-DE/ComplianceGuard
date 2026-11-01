# RUNBOOK.md — 启动 / 回滚 / 故障排查

> **状态：草案（随环境变化更新）** ｜ 最后更新：2026-11-01 ｜ 维护：统筹方 + Claude
>
> Harness 组件④：**架构约束与可恢复性**。开发/演示出问题时，照本文件操作，不要临场发挥。

---

## 1. 启动顺序（严格按序）

```bash
# 1) MySQL 服务（Windows 服务 MySQL82，通常开机自启）
sc query MySQL82

# 2) 建库建表 + 种子数据
python -m scripts.init_db
python -m scripts.seed_cases

# 3) 构建向量库（Chroma）
python -m scripts.build_index

# 4) 后端
python -m uvicorn backend.main:app --reload --port 8000
#    健康检查：curl http://127.0.0.1:8000/health

# 5) MCP 自检（不联网、不花钱）
python -m backend.mcp_server.server --selftest

# 6) 前端
cd frontend && npm run dev
```

## 2. 环境变量（`.env`，不入库）

| 键 | 说明 |
|---|---|
| `DATABASE_URL` | `mysql+pymysql://root:123456@localhost:3306/compliance_guard` |
| `JWT_SECRET` / `JWT_EXPIRE_HOURS` | 鉴权 |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | 判定/生成模型（OpenAI 兼容） |
| `CHROMA_DIR` | `D:\ComplianceGuard\data\chroma` |
| `NEO4J_*` | **默认不启用**，需要知识图谱时才配 |

## 3. 回滚手段（三级）

| 级别 | 操作 | 适用 |
|---|---|---|
| 代码 | `git revert <commit>` 或切回上一个 tag | 改坏了某次提交 |
| 数据 | 恢复 `scripts/` 下的备份 SQL（**执行前必须先导出**） | 误删数据 |
| 向量库 | 删除 `data/chroma/` 重建 `python -m scripts.build_index` | 索引脏了 |

## 4. 故障排查（按"现象 → 根因 → 处理"）

| 现象 | 根因 | 处理 |
|---|---|---|
| `import chromadb` 抛 `Descriptors cannot be created directly` | opentelemetry-proto 落后于 protobuf 7.x | 升级 opentelemetry-proto（见 `SKILL.md` S0） |
| 连不上 MySQL | 服务未启动 / 库不存在 | `sc query MySQL82`；跑 `init_db` 自建库 |
| 模型 429 / 超时 | 限流或网络 | 系统自动降级为**纯规则判定**，结果标 `incomplete`，不许当合规 |
| 前端跨域 | CORS 未开 | 后端已放行 `localhost:5173`，新端口需补 |
| 中文乱码 | GBK 控制台 | 代码不打印 emoji；文件显式 UTF-8 |

## 5. 演示前检查清单
- [ ] `/health` 200
- [ ] MCP `--selftest` 6 个工具
- [ ] 锚点集 30 条已入库、向量库已建
- [ ] 用真实罚单话术跑通一次"审查→命中→改写"
- [ ] `.env` 已填、无明文密钥进 git

---

## 变更记录
| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-11-01 | 建立启动顺序、回滚三级、故障表 | 项目启动 |
