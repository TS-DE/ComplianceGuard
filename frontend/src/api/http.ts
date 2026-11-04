import axios from 'axios'
import { ElMessage } from 'element-plus'
export interface Envelope<T> { code: number; msg: string; data: T; total?: number | null }
export interface Page<T> { items: T[]; total: number }
let unauthorized = false
export function resetUnauthorized() { unauthorized = false }
function fail(message: string, status?: number): never {
  if (status === 401) {
    localStorage.removeItem('token')
    if (!unauthorized) {
      unauthorized = true
      ElMessage.error(message)
      window.dispatchEvent(new Event('auth-expired'))
      if (location.pathname !== '/login') location.replace('/login')
    }
  } else ElMessage.error(message)
  throw new Error(message)
}
const http = axios.create({ baseURL: import.meta.env.VITE_API_BASE, timeout: 180000 })
http.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
// total与data分开保留，页面不依赖Axios响应对象，也不丢分页元数据。
http.interceptors.response.use(response => {
  const body: unknown = response.data
  if (!body || typeof body !== 'object' || !('code' in body) || !('data' in body)) return fail('服务返回格式异常')
  const value = body as Envelope<unknown>
  if (value.code !== 200) return fail(value.msg || '请求失败', value.code)
  response.data = value.data
  Reflect.set(response, 'pageTotal', value.total)
  return response
}, (error: unknown) => {
  if (axios.isAxiosError(error)) {
    const body: unknown = error.response?.data
    const message = body && typeof body === 'object' && 'msg' in body && typeof body.msg === 'string' ? body.msg : '网络请求失败，请稍后重试'
    return fail(message, error.response?.status)
  }
  return fail('请求失败')
})
/**
 * timeoutMs 可按请求覆盖：默认 180 秒够单条审查，但红队一次要生成 16 条再逐条判定，
 * 实测约 141 秒、与默认超时贴得太近，必须放宽到 300 秒，否则浏览器先超时而后端还在跑。
 */
export async function request<T>(
  method: string, url: string, data?: unknown, params?: object, timeoutMs?: number
): Promise<T> {
  const response = await http.request<T>({ method, url, data, params, ...(timeoutMs ? { timeout: timeoutMs } : {}) })
  return response.data
}
export async function page<T>(url: string, params?: object): Promise<Page<T>> {
  const response = await http.get<T[]>(url, { params })
  const total: unknown = Reflect.get(response, 'pageTotal')
  if (typeof total !== 'number') return fail('分页总数缺失')
  return { items: response.data, total }
}

/**
 * 取回二进制内容（原始素材内联预览：海报、录音、PDF）。
 *
 * 为什么不复用 request：上面的响应拦截器假定返回是 {code,msg,data} 信封，
 * Blob 没有 code 字段会被判成"服务返回格式异常"，所以这里绕开拦截器、单独挂鉴权头。
 * 也别改用 ?token= 查询参数：那会把令牌留在浏览器历史、服务器访问日志和referer里。
 */
export async function requestBlob(url: string, timeoutMs = 120000): Promise<Blob> {
  const token = localStorage.getItem('token')
  try {
    const response = await axios.get(`${import.meta.env.VITE_API_BASE}${url}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      responseType: 'blob',
      timeout: timeoutMs
    })
    return response.data as Blob
  } catch (error: unknown) {
    if (!axios.isAxiosError(error)) return fail('网络请求失败，请稍后重试')
    const status = error.response?.status
    // 出错时后端返回的是 JSON 信封，但 responseType=blob 把它包成了 Blob，
    // 不读出来就只能显示"请求失败"，商家永远不知道是"素材已被清理"还是"没权限"。
    let message = error.response?.statusText || '请求失败'
    const body: unknown = error.response?.data
    if (body instanceof Blob) {
      try {
        const parsed = JSON.parse(await body.text()) as Envelope<unknown>
        if (parsed?.msg) message = parsed.msg
      } catch {
        // 非 JSON 错误体（网关超时等）保留 statusText。
      }
    }
    return fail(message, status)
  }
}
