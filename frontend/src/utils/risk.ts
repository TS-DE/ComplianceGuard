/**
 * 风险语义的唯一映射表：score/incomplete → 视觉状态 → 文案。
 *
 * 为什么放 api/utils 而不是各组件里各写一份 if：
 * 后端 `score` 的取值域是 2/1/0/-1（db_schema.md），-1 是"判定未完成"，
 * **绝不能在任何展示层被当成合规**。一旦有第二个页面自己写了
 * `score !== 0 ? 成功 : 违规`，就会悄悄把未完成显示成没问题——这类 bug 没人报，
 * 因为它"看起来是对的"。所有页面必须走这里。
 *
 * OCP：将来加一档（例如"仅提示不计分"）只改这一张表，不改任何组件。
 */
export type RiskState = 'hard' | 'soft' | 'pending' | 'ok'

export interface RiskMeta {
  state: RiskState
  label: string
  /** CSS 变量名，组件只认它，不认色值 */
  color: string
  bg: string
}

export const RISK_META: Record<RiskState, RiskMeta> = {
  hard: { state: 'hard', label: '违规', color: 'var(--cg-hard)', bg: 'var(--cg-hard-bg)' },
  soft: { state: 'soft', label: '轻微风险', color: 'var(--cg-soft)', bg: 'var(--cg-soft-bg)' },
  pending: { state: 'pending', label: '判定未完成', color: 'var(--cg-pending)', bg: 'var(--cg-pending-bg)' },
  ok: { state: 'ok', label: '合规', color: 'var(--cg-ok)', bg: 'var(--cg-ok-bg)' }
}

/**
 * 判定 → 风险态。优先级：失败/未完成 > 硬违规 > 软命中 > 合规。
 * `error` 是批量审查里单条模型故障，同样归入 pending（铁律 5）。
 */
export function riskState(input: {
  score: number
  incomplete?: boolean | null
  error?: string | null
}): RiskMeta {
  if (input.error || input.incomplete || input.score === -1) return RISK_META.pending
  if (input.score === 0) return RISK_META.hard
  if (input.score === 1) return RISK_META.soft
  return RISK_META.ok
}

/**
 * 把后端 hits 的一条拍平成展示对象（DIP/LKP：组件不再自己钻 `hit.axes[0].evidence`）。
 * 后端字段名沿用 api_spec.md，不改语义，只做展示层聚合。
 */
export interface HitView {
  key: string
  axis: string
  axisLabel: string
  lawArticle: string
  itemNo: string | null
  quote: string
  reason: string | null
  severity: 'hard' | 'soft'
  downgraded: boolean
  downgradeReason: string | null
  detector: string | null
}
