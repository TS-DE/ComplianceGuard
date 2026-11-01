# db_schema.md — 数据契约

> **状态：生效（稳定契约，改动必须走迁移）** ｜ 最后更新：2026-11-01 ｜ 维护：统筹方
>
> 本文件是 MySQL 表结构与 Chroma collection 的**唯一真相**。
> 改这里之前先想清楚：**表结构错了，后面所有代码都要返工。**

---

## 1. MySQL：库名 `compliance_guard`

DSN：`mysql+pymysql://root:123456@localhost:3306/compliance_guard?charset=utf8mb4`

### 1.1 `users` — 账号

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK, AI | |
| username | VARCHAR(50) | UNIQUE, NOT NULL | 登录名 |
| password_hash | VARCHAR(255) | NOT NULL | bcrypt，**禁止存明文** |
| role | ENUM('admin','operator') | DEFAULT 'operator' | |
| is_active | TINYINT(1) | DEFAULT 1 | 停用即不能登录 |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | |

### 1.2 `clients` — 机构（CRUD 1）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK, AI | |
| name | VARCHAR(100) | NOT NULL | 机构名 |
| industry | VARCHAR(50) | DEFAULT 'medical_beauty' | 行业，为多切片预留 |
| contact | VARCHAR(100) | NULL | 联系人/电话 |
| plan | VARCHAR(30) | DEFAULT 'free' | 套餐（演示用） |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | |

### 1.3 `scripts` — 话术（CRUD 2）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK, AI | |
| client_id | BIGINT | FK→clients.id, NOT NULL, INDEX | 归属机构 |
| scene | VARCHAR(50) | NULL | 场景：双眼皮/热玛吉/美白/祛斑/植发 |
| content | TEXT | NOT NULL | 待审话术原文 |
| status | ENUM('pending','audited','archived') | DEFAULT 'pending' | |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | |

### 1.4 `audits` — 审查记录（CRUD 3，Agent 落库目标）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK, AI | |
| script_id | BIGINT | FK→scripts.id, NOT NULL, INDEX | |
| score | TINYINT | NOT NULL | **2 合规 / 1 轻微 / 0 违规 / -1 未完成** |
| hit_count | INT | DEFAULT 0 | 命中条数（列表页快速展示） |
| hits_json | JSON | NULL | 每条：`{axis, pattern, level, quote, law_article, reason}` |
| law_refs_json | JSON | NULL | 引用的法条：`[{code:"广告法第16条", text:"...", source_id:"..."}]` |
| rewritten_text | TEXT | NULL | Agent2 改写稿 |
| rewrite_passed | TINYINT(1) | NULL | 改写稿二次审查是否通过（NULL=未做） |
| model | VARCHAR(50) | NULL | 判定模型名 |
| prompt_tokens | INT | DEFAULT 0 | 成本计量 |
| completion_tokens | INT | DEFAULT 0 | |
| cost | DECIMAL(10,6) | DEFAULT 0 | 估算元 |
| latency_ms | INT | DEFAULT 0 | 端到端耗时 |
| incomplete | TINYINT(1) | DEFAULT 0 | 1=有轴调用失败，**不许当合规** |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP, INDEX | 报告按时间窗聚合 |

### 1.5 `rules` — 规则库（CRUD 4，Agent 工具读取）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK, AI | |
| axis | VARCHAR(40) | NOT NULL, INDEX | 规则轴枚举（见 §3） |
| law_article | VARCHAR(80) | NOT NULL | 如 `广告法第16条` |
| pattern | VARCHAR(200) | NOT NULL | 违规模式描述 |
| level | ENUM('hard','soft') | NOT NULL | hard=一票否决 |
| example_bad | TEXT | NULL | 反例原文 |
| version | INT | DEFAULT 1 | **改规则必须 +1** |
| enabled | TINYINT(1) | DEFAULT 1 | |
| created_at / updated_at | DATETIME | | |

### 1.6 关系与外键策略
```
clients 1 ──< scripts 1 ──< audits
rules（独立字典表，被 Agent 读取）
users（独立，仅鉴权）
```
- 外键**建立**但 `ON DELETE RESTRICT`（禁止级联删业务数据）
- 所有表 `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci`

---

## 2. Chroma：持久化目录 `data/chroma`

### 2.1 collection `law_articles`
| 项 | 值 |
|---|---|
| 文档 | 法条条文（chunk，每 chunk ≤ 400 字，带条号前缀） |
| metadata | `{code: "广告法第16条", source: "中华人民共和国广告法", chapter: "医疗广告"} `|
| 来源 | `data/law/*.md` |

### 2.2 collection `case_fines`（**锚点集，不用 AI 生成**）
| 项 | 值 |
|---|---|
| 文档 | 罚单案例的"违规原话 + 官方定性" |
| metadata | `{case_id, penalty_amount, authority, year, category}` |
| 来源 | `data/cases/*.json`（SAMR 公开通报） |
| 目标条数 | 20–30 |

**文件格式（`data/cases/case_001.json`）**：
```json
{
  "case_id": "samr_2025_002",
  "title": "上海泰康拜博贝斯特口腔医院违法广告案",
  "authority": "上海市市场监管局",
  "year": 2024,
  "penalty_amount": 613700,
  "violation_quote": "这个能保证你做完之后能往上走1—3个色度；所以这个是非常的安全，而且非常的高效",
  "official_ruling": "对医疗服务作出表示功效、安全性的断言或者保证",
  "law_articles": ["广告法第16条"],
  "category": "功效/安全性断言"
}
```

---

## 3. 规则轴枚举（`rules.axis` 取值，先定 8 条）

| axis | 含义 | 主要法条 | 默认 level |
|---|---|---|---|
| `absolute_terms` | 绝对化用语（最高/第一/顶级/永久） | 广告法第9条 | hard |
| `efficacy_claim` | 功效断言/保证（保证白一个色度） | 广告法第16条 | hard |
| `safety_guarantee` | 安全性保证（零风险/无副作用） | 广告法第16、18条 | hard |
| `disease_treatment` | 疾病治疗功能暗示（消炎/祛斑=治病） | 广告法第17、18条 | hard |
| `false_quantify` | 无法验证的量化承诺（3天见效/百分百） | 广告法第28条 | hard |
| `before_after` | 术前术后对比/患者形象作证明 | 医疗广告管理办法 | soft |
| `inducement` | 制造焦虑式诱导（不做就毁容） | 广告法第9条(妨碍社会公共秩序) | soft |
| `false_authority` | 虚构权威背书（三甲主任/专家推荐） | 广告法第28条 | soft |

> 8 条轴是**起点**，不是终点：跑完锚点集后按漏杀结果增补，改动必须 bump `rules.version`。

---

## 变更记录
| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-11-01 | 建立 5 表 + 2 collection + 8 轴枚举 | 项目启动，D1 建库依据 |
