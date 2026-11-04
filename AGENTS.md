# AGENTS.md — Agent 专业化分工

> **状态：草案（业务 Agent 待 D3/D4 填充流程，开发子 Agent 已生效）** ｜ 最后更新：2026-11-01 ｜ 维护：统筹方 + Claude
>
> Harness 组件②：**窄角色、并行分工，一个 Agent 只做一类事**。
> 本文件分两部分：**A. 开发子 Agent**（写代码的）与 **B. 业务 Agent**（产品里的 5 个智能体）。

---

## A. 开发子 Agent（开发期使用，可并行）

| 子 Agent | 职责边界 | 允许改的目录 | 禁止 |
|---|---|---|---|
| **DB Agent** | 表结构、迁移、种子数据 | `backend/models/`、`backend/db/`、`scripts/`、`db_schema.md` | 改业务逻辑 |
| **Backend Agent** | 路由 / schema / service / crud | `backend/api/`、`backend/schemas/`、`backend/crud/`、`backend/services/` | 改表结构、改前端 |
| **Agent Agent** | 5 个智能体 + MCP 工具 | `backend/agents/`、`backend/tools/`、`backend/mcp_server/`、`backend/rag/`、`backend/parse/` | 改 CRUD 接口 |
| **Frontend Agent** | Vue3 页面与联调 | `frontend/` | 改后端 |
| **Test Agent** | pytest 用例与验收脚本 | `tests/` | 改被测代码 |
| **Doc Agent**（后台/定期） | 文档审校：删过时、并重复、标过时 | 根目录 `*.md` | 改代码 |

**委派纪律**：
1. 一次只委派一个目录范围的任务，避免两个 Agent 同改一个文件；
2. 每个子 Agent 交付时**必须自己跑通本模块测试**再交；
3. 跨目录改动由统筹方协调，不由子 Agent 自行越界。

---

## B. 业务 Agent（产品内的 5 个智能体）

> 每个 Agent 的节点流程在对应阶段补全（A1/A2 → D3；A3–A5 → D4）。
> **现在只登记职责与工具，流程留 TODO。**

### A1 合规审查 Agent（ComplianceAuditAgent）★核心
- **职责**：一段话术 → 两层判定 → 命中法条+原文引文+分数
- **工具**：`rag_search_law`、`db_query_rules`、`db_query_violation_history`、`parse_source`
- **入口有两个**：① 文本（人工粘贴 / 话术库）；② `source_id` —— 商家递来海报、扫描件、录音时，
  A1 用 `parse_source` 自己取回逐条话术与溯源，不依赖有人先复制粘贴
- **流程**：TODO（D3 补：归一→硬规则→规则加载→RAG→语义判定→引文校验→聚合→落库）
- **铁律**：分数由代码算；每条命中双引文（用户原文 + 法条）；引不出法条即作废

### A2 违规改写 Agent（RewriteAgent）
- **职责**：改写稿 + **二次过审**
- **工具**：`rag_search_law`、`audit_recheck`
- **流程**：TODO（D3 补）
- **铁律**：二次审查不通过必须标"改写失败"，不许假装成功

### A3 红队攻击 Agent（RedTeamAgent）
- **职责**：扮销售生成三级递进擦边话术
- **工具**：`db_query_scenes`
- **流程**：一次生成三档违规+合规对照→严格矩阵校验→scripts来源/meta持久化。
- **边界**：只做广告法域；不生成涉政涉黄涉暴

### A4 监管裁判 Agent（JudgeAgent）
- **职责**：独立判定红队样本 → 漏杀清单
- **工具**：`rag_search_law`、`db_query_rules`、`db_save_redteam_result`
- **流程**：逐条复用A1并落audits→TP/FN/FP/TN或unjudged→回写meta→按run聚合。
- **铁律**：判定前先跑人类锚点集，锚点上崩了本轮作废

### A5 审计报告 Agent（AuditReportAgent）
- **职责**：聚合 MySQL 记录 → 日报/压测报告
- **工具**：内部仓储聚合（非新增MCP工具）
- **流程**：仓储SQL聚合→固定模板日报/压测报告；默认零模型成本，数字不由模型生成。
- **铁律**：只解释已有数字，**禁止生成新事实**

---

## 变更记录
| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-11-01 | 建立开发子 Agent 分工 + 5 个业务 Agent 职责登记 | D1 开工 |
