# db_schema.md — 数据契约

> **状态：生效（稳定契约，改动必须走迁移）** ｜ 最后更新：2026-11-01 ｜ 维护：统筹方 + Claude
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
| role | ENUM('admin','operator') | NOT NULL, DEFAULT 'operator' | |
| is_active | TINYINT(1) | NOT NULL, DEFAULT 1 | 停用即不能登录 |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

### 1.2 `clients` — 机构（CRUD 1）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK, AI | |
| name | VARCHAR(100) | NOT NULL | 机构名 |
| industry | VARCHAR(50) | NOT NULL, DEFAULT 'medical_beauty' | 行业，为多切片预留 |
| contact | VARCHAR(100) | NULL | 联系人/电话 |
| plan | VARCHAR(30) | NOT NULL, DEFAULT 'free' | 套餐（演示用） |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

### 1.3 `scripts` — 话术（CRUD 2）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK, AI | |
| client_id | BIGINT | FK→clients.id, NOT NULL, INDEX | 归属机构 |
| scene | VARCHAR(50) | NULL | 场景：双眼皮/热玛吉/美白/祛斑/植发 |
| source | ENUM('manual','redteam') | NOT NULL, DEFAULT 'manual' | 来源 |
| redteam_meta | JSON | NULL | run_id、target_axis、strength、strategy、expected_violation；判定后追加verdict/actual_axes/audit_id |
| content | TEXT | NOT NULL | 待审话术原文 |
| status | ENUM('pending','audited','archived') | NOT NULL, DEFAULT 'pending' | |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

### 1.4 `audits` — 审查记录（CRUD 3，Agent 落库目标）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK, AI | |
| script_id | BIGINT | FK→scripts.id, NOT NULL, INDEX | |
| score | TINYINT | NOT NULL, **CHECK `ck_audits_score`: score BETWEEN -1 AND 2** | **2 合规 / 1 轻微 / 0 违规 / -1 未完成**，取值域由数据库强制 |
| hit_count | INT | NOT NULL, DEFAULT 0 | 命中条数（列表页快速展示） |
| hits_json | JSON | NULL | 每条：`{axis, pattern, level, quote, law_article, reason}` |
| law_refs_json | JSON | NULL | 引用的法条：`[{code:"广告法第16条", text:"...", source_id:"..."}]` |
| rewritten_text | TEXT | NULL | Agent2 改写稿 |
| rewrite_passed | TINYINT(1) | NULL | 改写稿二次审查是否通过（NULL=未做） |
| model | VARCHAR(50) | NULL | 判定模型名 |
| prompt_tokens | INT | NOT NULL, DEFAULT 0 | 成本计量 |
| completion_tokens | INT | NOT NULL, DEFAULT 0 | |
| cost | DECIMAL(10,6) | NULL, DEFAULT NULL | NULL=未配置单价未计价；0=确为零成本；估算元 |
| latency_ms | INT | NOT NULL, DEFAULT 0 | 端到端耗时 |
| incomplete | TINYINT(1) | NOT NULL, DEFAULT 0 | 1=有轴调用失败，**不许当合规** |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP, INDEX `ix_audits_created_at` | 报告按时间窗聚合 |

### 1.5 `rules` — 规则库（CRUD 4，Agent 工具读取）

> **v0.1.1 变更（2026-11-01）：新增 `detector` 与 `exemptions` 两列。**
> 原因：**"严重度"与"检测手段"是两个正交维度**——hard 违规也可能只能靠语义判定
> （如"保证做完能往上走 1—3 个色度"里没有任何违禁词），soft 违规也可能正则秒查。
> 同时把法条自带的"不适用情形"独立成字段，避免与 pattern 混在一起导致误杀。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT | PK, AI | |
| axis | VARCHAR(40) | NOT NULL, INDEX `ix_rules_axis` | 规则轴枚举（见 §3） |
| law_article | VARCHAR(80) | NOT NULL | 如 `广告法第16条` |
| pattern | VARCHAR(200) | NOT NULL | **什么算违规**（违规模式描述） |
| level | ENUM('hard','soft') | NOT NULL | **严重度**：hard=一票否决；soft=累计扣分 |
| **detector** | **ENUM('keyword','regex','semantic','llm_judge')** | **NOT NULL, DEFAULT 'llm_judge'** | **用什么方法查**（见 §3.2） |
| **exemptions** | **JSON** | NULL | **法律上不算违规的情形**（白名单），见 §3.3 |
| example_bad | TEXT | NULL | 反例原文（给判定器做 few-shot） |
| version | INT | NOT NULL, DEFAULT 1 | **改规则必须 +1** |
| enabled | TINYINT(1) | NOT NULL, DEFAULT 1 | |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| updated_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP **ON UPDATE CURRENT_TIMESTAMP** | 库侧自动刷新 |

**三列的分工（一句话）**：
`pattern` 说"**什么算违规**"，`exemptions` 说"**什么看起来像违规但其实不算**"，`detector` 说"**用什么方法去查**"。
**三者是独立维度**，混在一起会让判定器和读代码的人都分不清。

### 1.6 关系与外键策略
```
clients 1 ──< scripts 1 ──< audits
rules（独立字典表，被 Agent 读取）
users（独立，仅鉴权）
```
- 外键**建立**但 `ON DELETE RESTRICT`（禁止级联删业务数据）
- **带 DEFAULT 的列一律 NOT NULL**（D1 落地决策）：杜绝"有默认值却写了 NULL"的第三种状态
- 建表脚本 `scripts/init_db.py` 生成 `CREATE TABLE IF NOT EXISTS`，可重复执行
- 分数取值域由 `CHECK` 约束在库侧强制（Harness ⑤ 约束自动化）
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

## 3. 规则轴枚举（`rules.axis` 取值，先定 11 条）

| axis | 含义 | 主要法条 | 默认 level |
|---|---|---|---|
| `absolute_terms` | 绝对化用语（最高/第一/顶级/永久） | 广告法第9条(三) + 绝对化用语执法指南 | hard |
| `efficacy_claim` | 功效断言/保证（保证白一个色度） | 广告法第16条(一) | hard |
| `safety_guarantee` | 安全性保证（零风险/无副作用/绝对安全） | 广告法第16条(一)、第18条(一) | hard |
| `disease_treatment` | 疾病治疗功能暗示（消炎/祛斑=治病） | 广告法第17条、第18条(二) | hard |
| `false_quantify` | 无法验证的量化承诺（3天见效/百分百） | 广告法第28条(二)(四) | hard |
| `cure_rate` | **说明治愈率/有效率**（含数字或百分比） | 广告法第16条(二) | hard |
| `derogatory_compare` | **贬低/对比同行**（比别家安全、别家做不到） | 广告法第13条、第16条(三) | hard |
| `endorsement` | **以代言人/推荐官/体验官/患者名义作推荐证明** | 广告法第16条(四)、医美指南第五条(五)(六) | soft |
| `before_after` | 术前术后对比/患者形象作证明 | 医疗广告管理办法第7条(六) | soft |
| `inducement` | 制造容貌焦虑式诱导（不做就毁容/显老） | 广告法第9条(七)、医美指南第五条(一) | soft |
| `false_authority` | 虚构权威背书（三甲主任/专家推荐/冒用机构名义） | 广告法第28条(三)、医美指南第八条 | soft |

> ⚠️ **明确不做**：`unapproved_scope`（宣传未经审批的诊疗科目/服务项目）——系统无法核验《医疗广告审查证明》，
> 做不了就写"不做"，**不许假装能做**（对应医美指南第五条(二)(三)）。

> 10 条轴是**起点**，不是终点：跑完锚点集后按漏杀结果增补，改动必须 bump `rules.version`。

### 3.1 轴与检测手段的分配（D2 灌种子时按此填 `detector`）

| axis | detector | 为什么用这个 |
|---|---|---|
| `absolute_terms` | `regex` | "最高级/最佳/第一/顶级"可正则枚举；配 `exemptions` 排除"奖项称号/自我比较"等 9 种 |
| `efficacy_claim` | `llm_judge` | 组合语义（"保证…能…色度"）无显式违规词，正则查不出 |
| `safety_guarantee` | `keyword` + `llm_judge` | "零风险/无副作用/绝对安全"可词表命中；变体（"稳如泰山"）需语义 |
| `disease_treatment` | `llm_judge` | "祛斑/消炎"是否被当作治病功能，取决于语境 |
| `false_quantify` | `regex` | "7天见效/100%/一次搞定"数字+时间可正则 |
| `cure_rate` | `regex` | "治愈率/有效率+数字"结构固定 |
| `derogatory_compare` | `llm_judge` | "比别家安全/别家做不到"是否为贬低对比，需语境 |
| `endorsement` | `llm_judge` | "推荐官/体验官/亲测"是否构成广告代言，需语境判断 |
| `before_after` | `llm_judge` | "前后对比图/患者作证"多为描述性表达 |
| `inducement` | `llm_judge` | 是否制造容貌焦虑，纯语义 |
| `false_authority` | `llm_judge` | "三甲主任"真伪无法从文本判定，只能判"是否用作背书" |

### 3.2 `detector` 枚举语义

| 值 | 含义 | 典型耗时 | 特性 |
|---|---|---|---|
| `keyword` | 词表命中 | ~1 ms | 高精确、零成本；漏变体 |
| `regex` | 正则结构匹配 | ~1 ms | 能抓"数字+时间+功效"这类结构 |
| `semantic` | 向量/小模型相似度 | ~50 ms | **本期不启用**（需额外模型，7 天不做） |
| `llm_judge` | 大模型读「法条 + pattern + exemptions + 候选」后判定 | ~1–5 s | 能处理组合语义；有成本、有不稳定性 |

**路由规则**：按 `detector` 分组执行 —— 先跑 `keyword`/`regex`（廉价、确定性），
再跑 `llm_judge`（昂贵、有概率），且**廉价层命中 hard 时不阻断语义层**（语义层可能发现另一类违规）。
**不启用 `semantic`**，字段保留供后续演进。

### 3.3 `exemptions` 结构与用法

范围豁免 `scope_exemptions` 的四条原文及出处保存在代码常量 `backend/core/constants.py::SCOPE_EXEMPTIONS`，在规则判定前使用，不新增数据库表，也不混入单条规则的 `exemptions`。

**JSON 数组**，每项含 `text`（豁免情形的法条原文或概述）与 `source`（出处，可追溯）：

```json
[
  {"text": "仅表明商品经营者的服务态度或者经营理念、企业文化、主观愿望的",
   "source": "广告绝对化用语执法指南 第五条(一)"},
  {"text": "仅用于对同一品牌或同一企业商品进行自我比较的",
   "source": "广告绝对化用语执法指南 第六条(一)"},
  {"text": "依据国家有关规定评定的奖项、称号中含有绝对化用语的",
   "source": "广告绝对化用语执法指南 第六条(五)"}
]
```

**用法（判定器必须遵守）**：
1. 候选话术先按 `pattern` 判"是否命中"；
2. 命中后**再按 `exemptions` 判"是否属于豁免"**；
3. 属于豁免 → **该条命中作废**，并在 `hits_json` 记 `exempted_by`（保留痕迹，可审计）；
4. **禁止把 exemptions 塞进 `pattern` 当反例**——两者方向相反，混写会让判定器把"合法"当"违规的软化版"处理。

**典型例**：
- 话术 `我们要做最好的医美服务` → 命中 `absolute_terms`（"最好的"）
- 但豁免命中"仅表明经营理念/主观愿望" → **判合规**，并记录 `exempted_by`
- 若没有 `exemptions`，这条会被误杀 —— 而豁免依据是法律自己给的（执法指南第五条），
  不抄下来就是白白制造误杀。

---

## 变更记录
| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-11-01 | 建立 5 表 + 2 collection + 8 轴枚举 | 项目启动，D1 建库依据 |
| 2026-11-01 | 补全 NOT NULL、`ck_audits_score` CHECK、`updated_at` ON UPDATE、索引名 | D1 建库落地，代码与文档对齐 |
| 2026-11-01 | rules 增 `detector`（检测手段）+ `exemptions`（法定豁免清单），并补 §3.1 轴分配表 / §3.2 detector 语义 / §3.3 exemptions 用法 | **严重度与检测手段是正交维度**；法条自带的"不适用情形"须独立成白名单，否则误杀 |
| 2026-11-01 | 轴从 8 条扩到 10 条（新增 `cure_rate` 治愈率、`endorsement` 广告代言） | 《广告法》第16条(二)显式禁止说明治愈率；《医美广告执法指南》第五条(六)单列"推荐官/体验官" |
