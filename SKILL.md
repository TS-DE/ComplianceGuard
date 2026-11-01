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
| S1 | FastAPI 统一返回体 + 全局异常 | TODO（D1 验证后填） | — |
| S2 | SQLAlchemy 2.0 建模（Mapped/mapped_column） | TODO（D1） | — |
| S3 | JWT 鉴权依赖注入 | TODO（D1） | — |
| S4 | Pydantic V2 校验与分页参数 | TODO（D1） | — |
| S5 | Chroma collection 建库与 metadata 过滤 | TODO（D2） | — |
| S6 | MCP 工具注册与 selftest | TODO（D2） | — |
| S7 | LangChain 工具调用（Tool 绑定） | TODO（D3） | — |
| S8 | 引文子串校验（quote → 原文定位） | TODO（D3） | — |
| S9 | Vue3 + Element Plus 表格/表单页骨架 | TODO（D5） | — |

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

## 变更记录
| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-11-01 | 建立索引与 S0（Chroma protobuf 坑） | 启动前环境修复 |
