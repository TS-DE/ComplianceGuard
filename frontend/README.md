# frontend — 视觉与组件说明

> 状态：生效 ｜ 最后更新：2026-11-05 ｜ 维护：前端实施者
>
> **改版以本文为基准**：色阶、字体、层级规则都锁在 `src/styles/tokens.css` 里，
> 组件内禁止写死色值。要改视觉，先改本文的理由，再改 token，最后才动组件。

## 一、设计说明：为什么是"案卷"而不是"仪表盘"

这个产品做的事是**对着法条审一句话**，工作对象是文本与证据，不是流量指标。
所以视觉语言借"案卷 / 审校"，而不是借 SaaS 仪表盘。四条主张：

**1. 底色是冷灰档案纸，不是暖米色。**
`--cg-paper #F6F7F9`。暖底 + 陶土色强调是通用生成页的通病，且与"监管、留痕"的气质相反。

**2. 层级只靠 1px 边线与留白，全站零阴影。**
`--cg-shadow: none`。证据不需要被"托起来"显得重要；阴影堆叠只会让命中卡片像营销模块。
圆角只有一档 `--cg-radius: 3px`，胶囊 `999px` 仅用于风险标签——两者刻意区分：
标签是"判定态"，卡片是"卷面"。

**3. 语义色是信息，不是装饰。** 四种颜色只允许出现在风险表达上：

| token | 含义 | 用在哪 |
|---|---|---|
| `--cg-hard #B0362A` 朱红 | 硬违规（触法条明文） | score=0、hard 命中 |
| `--cg-soft #A2670E` 赭黄 | 轻微 / 软命中 / 已降级 | score=1、soft 命中 |
| `--cg-pending #5A6673` 石墨 | **判定未完成** | score=-1、模型故障 |
| `--cg-ok #1F6B5B` 青 | 合规 | score=2 |

朱红取自印泥、青取自青铜印章的铜绿，都是这个行业的实物颜色，不是随便挑的"品牌色"。
`RiskBadge` / `ScoreRing` / `utils/risk.ts` 是唯一的映射出口——**任何页面都不许自己写
`score !== 0 ? 绿 : 红`**，那样会把"判定未完成"染成合规（本项目最贵的一类错）。

**4. 一个页面只允许一处强调色。** `--cg-accent` 只用于当前主操作与导航选中态。

**排版**：界面与数字用无衬线（PingFang / 微软雅黑 / MiSans），
**引文与法条原文用衬线**（宋体 / Source Han Serif），且 `tabular-nums` 全局开启。
理由不是好看：这是全站唯一"一眼分清证据与界面"的手段——`HitCard` 里的原文片段与
法条正文走衬线 + 左侧 3px 竖线，像判决书里的批注；UI 文案一律无衬线。
这是我希望被人记住的那一处，其余保持安静。

**克制的边界**：不做"合规认证 / 官方背书"类徽章（法律边界）；不做通用内容审核入口；
免责声明每页常驻（侧栏底部 + 页面内），字号小但可读，不做成灰色水印。

**不做的事**：不引入 Tailwind、不引入图标库（本轮只允许 ECharts 与 diff 两个新依赖，
导航因此改用标题首字作字标）、不加第四套状态管理、不换 Element Plus。

## 二、组件清单与用法

目录规模守 CLAUDE.md §3.1：每个目录 `.vue` ≤3，超了就按类别开子目录。

| 组件 | 位置 | 职责（唯一变化原因） | 关键 props |
|---|---|---|---|
| `RiskBadge` | `components/risk/` | 把一个判定映射成四态标签 | `state` 或 `score/incomplete/error`、`note`、`plain` |
| `ScoreRing` | `components/risk/` | 环形色块表达判定；**刻意不是百分制** | `score`、`incomplete`、`hitCount`、`size` |
| `HitCard` | `components/risk/` | 一条命中的完整交代：片段 / 法条 / 理由 / 等级 | `hit: HitView`、`contextBefore/After`、`lawText`、事件 `locate`、`load-law` |
| `StatCard` | `components/data/` | 一个数字 + 它的口径（无 caption 视为不合格） | `label`、`value`、`caption`、`tone` |
| `EmptyState` | `components/data/` | 空态必须给出下一步动作 | `title`、`hint`、`actionText` + 事件 `action` |
| `DiffView` | `components/data/` | 改写前后词级差异 + 二次过审态 | `before`、`after`、`passed`、`recheckScore` |
| `StepProgress` | `components/layout/` | 摄取流程顺序指示 + 步骤跳转 | `steps`、`current`、`done` + 事件 `go` |

`HitCard` 只接**拍平后的 `HitView`**（`utils/risk.ts` 定义），不接受整行 audit 对象：
组件里出现 `row.hits_json[0].evidence[1]` 这种链式穿透，后端结构一变就要改三个页面（LKP/ISP）。

## 三、新增依赖

| 包 | 用途 | 为什么不是自己写 |
|---|---|---|
| `diff@9`（jsdiff） | `DiffView` 的词级差异 | 差异算法错得很安静（少标一个词没人发现），这类轮子不自己造 |

ECharts 尚未引入；工作台趋势图（A4 步骤）需要时再装，届时在此登记。

## 四、检查一个页面是否合格

1. 1280px 宽度下不破版，横向不出现整体滚动条；
2. 风险态全部走 `RiskBadge`/`riskState`，页面里没有自己写的颜色三元表达式；
3. 每个数字有口径说明（时间窗、是否含未完成）；
4. 免责声明可见；改写文案带"内部使用建议"；
5. 空态有动作按钮，不是"暂无数据"了事；
6. 键盘 Tab 能走到所有操作且焦点可见；`prefers-reduced-motion` 下不动效；
7. `npm run build`（含 `vue-tsc --noEmit`）零错误。
