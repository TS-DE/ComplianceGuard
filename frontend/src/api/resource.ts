import { page, request } from './http'
export interface Client { id: number; name: string }
export interface ScriptRow { id: number; client_id: number; scene: string | null; content: string; status: string; created_at: string }
export interface ScriptInput { client_id: number; scene: string | null; content: string }
export interface Hit { axis: string; law_article: string; quote: string }
export interface AuditResult { score: number; hit_count: number; hits: Hit[]; incomplete: boolean; disclaimer: string }
export const resources = (name: 'clients' | 'scripts' | 'audits' | 'rules') => ({
  list: <T>(params?: object) => page<T>(`/${name}`, params),
  get: <T>(id: number) => request<T>('GET', `/${name}/${id}`),
  create: <T>(data: unknown) => request<T>('POST', `/${name}`, data),
  update: <T>(id: number, data: unknown) => request<T>('PUT', `/${name}/${id}`, data),
  remove: (id: number) => request<{ id: number }>('DELETE', `/${name}/${id}`)
})
export const scripts = resources('scripts')
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
export interface LawArticleRow { code: string; article_no: number; text: string }
export interface LawArticle { doc: string; source: string; code: string; article_no: number; text: string; articles: LawArticleRow[] }
export const lawArticle = (code: string) => request<LawArticle>('GET', '/law/article', undefined, { code })
