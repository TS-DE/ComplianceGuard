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
export async function request<T>(method: string, url: string, data?: unknown, params?: object): Promise<T> {
  const response = await http.request<T>({ method, url, data, params })
  return response.data
}
export async function page<T>(url: string, params?: object): Promise<Page<T>> {
  const response = await http.get<T[]>(url, { params })
  const total: unknown = Reflect.get(response, 'pageTotal')
  if (typeof total !== 'number') return fail('分页总数缺失')
  return { items: response.data, total }
}
