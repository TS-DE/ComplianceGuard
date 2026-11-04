import { page, request } from './http'
export interface Client { id: number; name: string }
export interface ScriptRow { id: number; client_id: number; scene: string | null; content: string; status: string; created_at: string }
export interface ScriptInput { client_id: number; scene: string | null; content: string }
export interface Hit { axis: string; law_article: string; quote: string; item_no?: string | null; reason?: string | null }

// 风险轴中文名：界面上直接显示英文变量名（efficacy_claim）商家看不懂，
// 而"看不懂为什么违规"会直接被当成误杀。
export const AXIS_LABELS: Record<string, string> = {
  absolute_terms: '绝对化用语',
  efficacy_claim: '功效断言',
  safety_guarantee: '安全性保证',
  disease_treatment: '疾病治疗功能',
  false_quantify: '虚假量化承诺',
  cure_rate: '治愈率/有效率',
  derogatory_compare: '贬低同行',
  endorsement: '代言推荐',
  before_after: '前后效果对比',
  inducement: '容貌焦虑诱导',
  false_authority: '虚构权威'
}
export const axisLabel = (axis: string) => AXIS_LABELS[axis] ?? axis
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
  // 审查记录必须能直接看到被审的原话术：只给 script_id 的话，
  // 商家要跳回话术库再搜一遍，也没法复制原文去对照修改。
  script_content: string | null
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

// 压测前先问后端"这一轮会用哪些轴/哪版规则/哪个模型"，
// 否则界面只显示"16 条"，没人知道到底在测什么，结果也无法与规则改动对应。
export interface RedTeamAxisOption {
  axis: string; available: boolean
  version: number | null; detector: string | null
  law_article: string | null; pattern: string | null
}
export interface RedTeamOptions {
  model: string | null
  axes: RedTeamAxisOption[]
  plan: {
    per_axis_samples: number; description: string
    sample_total_for_all_axes: number; expected_seconds: string; note: string
  }
}
export const redTeamOptions = () => request<RedTeamOptions>('GET', '/redteam/options')
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

// 批量导入：商家给的是整页文档而不是一条条数据，所以走 multipart 上传 / 粘贴切分。
// 两段式（先预览再入库）在界面上强制：切分不可能百分百正确，必须允许人工剔除误切片段。
export interface ImportResult {
  source: string; count: number; items: string[]; created: number; script_ids: number[]
}
export const importScripts = (form: FormData) =>
  request<ImportResult>('POST', '/scripts/import', form, undefined, 180000)

// 批量审查：商家一次粘贴多条后，必须能一次审完，否则还是要逐条点。
// 后端顺序执行（单条约 6 秒），上限 20 条，因此超时放宽到 5 分钟。
export interface BatchAuditItem {
  script_id: number
  audit_id?: number
  score: number
  hit_count: number
  incomplete: boolean
  hits: Hit[]
  cost: string | null
  latency_ms: number
  error?: string
}
export const auditBatch = (clientId: number, scriptIds: number[]) =>
  request<{ count: number; results: BatchAuditItem[] }>(
    'POST', '/audit/batch', { client_id: clientId, script_ids: scriptIds }, undefined, 300000)
