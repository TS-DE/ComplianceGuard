import { page, request } from './http'
export interface Client { id: number; name: string }
export interface ScriptRow { id: number; client_id: number; scene: string | null; content: string; status: string; created_at: string }
export interface ScriptInput { client_id: number; scene: string | null; content: string }
export interface Hit { axis: string; law_article: string; quote: string; item_no?: string | null }
export interface AuditResult { score: number; hit_count: number; hits: Hit[]; incomplete: boolean; disclaimer: string }
export const resources = (name: 'clients' | 'scripts' | 'audits' | 'rules') => ({
  list: <T>(params?: object) => page<T>(`/${name}`, params),
  get: <T>(id: number) => request<T>('GET', `/${name}/${id}`),
  create: <T>(data: unknown) => request<T>('POST', `/${name}`, data),
  update: <T>(id: number, data: unknown) => request<T>('PUT', `/${name}/${id}`, data),
  remove: (id: number) => request<{ id: number }>('DELETE', `/${name}/${id}`)
})
export const scripts = resources('scripts')
export const audits = resources('audits')
export const rules = resources('rules')
export const clients = resources('clients')

// 审查记录行：cost 由后端 Decimal 序列化为字符串或 null（null=未配置单价未计价，不等于 0 元）。
export interface AuditRow {
  id: number; script_id: number; score: number; hit_count: number
  hits_json: Hit[] | null; law_refs_json: { code?: string }[] | null
  rewritten_text: string | null; rewrite_passed: boolean | null
  model: string | null; prompt_tokens: number; completion_tokens: number
  cost: string | null; latency_ms: number; incomplete: boolean; created_at: string
}
export interface RuleRow {
  id: number; axis: string; law_article: string; pattern: string
  level: string; example_bad: string | null; enabled: boolean; version: number
  detector: string | null; exemptions: { text?: string; source?: string }[] | null
  created_at: string; updated_at: string
}
export interface ClientRow {
  id: number; name: string; industry: string | null
  contact: string | null; plan: string | null; created_at: string
}
export interface DailyReport {
  total: number; incomplete: number; compliant: number; violations: number
  average_latency_ms: string; cost: string | null; unpriced: number
  known_cost_subtotal: string | null; date: string
  by_axis: Record<string, number>; violation_rate: number; summary: string; disclaimer: string
}
export const rewriteAudit = (id: number) =>
  request<{ rewritten_text?: string | null; rewrite_passed?: boolean | null; recheck?: unknown }>('POST', `/audit/${id}/rewrite`)

// ---------- 红队压测 ----------
// 后端约束：scenes 恰好 1 个、axes 1~4 个且限定 4 类、strength 只接受 'all'。
export const REDTEAM_AXES = [
  { value: 'efficacy_claim', label: '功效断言' },
  { value: 'safety_guarantee', label: '安全性保证' },
  { value: 'absolute_terms', label: '绝对化用语' },
  { value: 'inducement', label: '容貌焦虑诱导' }
] as const

export interface RedTeamCounts {
  TP_axis: number; TP_other: number; FN: number; FP: number; TN: number; unjudged: number
}
export interface RedTeamSample {
  id: number; client_id: number; scene: string; content: string
  meta: {
    verdict?: string; strength?: string; strategy?: string
    score?: number | null; actual_axes?: string[]; audit_id?: number
    latency_ms?: number; cost?: string | null
  }
}
export interface RedTeamGaps {
  run_id: string; generated: number; counts: RedTeamCounts
  fn_rate: number; axis_fn_rate: number; fp_rate: number; accuracy: number
  by_axis: Record<string, Partial<RedTeamCounts>>
  FN: RedTeamSample[]; FP: RedTeamSample[]
  samples: RedTeamSample[]; invalid_samples?: unknown[]
}
export const runRedTeam = (clientId: number, scene: string, axes: string[]) =>
  request<{ run_id: string; generated: number; script_ids: number[] }>(
    'POST', '/redteam/run', { client_id: clientId, scenes: [scene], axes, strength: 'all' },
    undefined, 300000)
export const redTeamGaps = (runId: string) =>
  request<RedTeamGaps>('GET', `/redteam/${encodeURIComponent(runId)}/gaps`)
// 日报接口的 date 是必填（不传返回 400），前端默认传本地当天，避免一进工作台就报错。
const pad = (n: number) => String(n).padStart(2, '0')
const today = () => {
  const now = new Date()
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}
export const dailyReport = (date?: string) =>
  request<DailyReport>('GET', '/reports/daily', undefined, { date: date || today() })
export async function allClients() {
  const items: Client[] = []
  let index = 1, total = 0
  do { const result = await page<Client>('/clients', { page: index++, page_size: 100 }); items.push(...result.items); total = result.total } while (items.length < total)
  return items
}
export const runAudit = (row: ScriptRow) => request<AuditResult>('POST', '/audit/run', { script_id: row.id, client_id: row.client_id })
export const rewrite = (id: number) => request<unknown>('POST', `/audit/${id}/rewrite`)
export const redteam = { run: (data: unknown) => request<unknown>('POST', '/redteam/run', data), gaps: (id: string) => request<unknown>('GET', `/redteam/${encodeURIComponent(id)}/gaps`) }
export const reports = { daily: (date: string) => request<unknown>('GET', '/reports/daily', undefined, { date }), redteam: (id: string) => request<unknown>('GET', `/reports/redteam/${encodeURIComponent(id)}`) }

// 法条追溯：命中条文 -> 该条原文 + 所属法规全表（用于「直达完整法规并定位高亮」）。
// 后端只读本地法规归档，不查向量库、不调模型，因此可随时点开且不产生费用。
export interface LawArticle {
  doc: string; source: string; code: string; article_no: number
  item_no: string | null; item_text: string | null; article_text: string
}
export const lawArticle = (code: string, itemNo?: string | null) =>
  request<LawArticle>('GET', '/law/article', undefined, itemNo ? { code, item_no: itemNo } : { code })
