import { request } from './http'
export interface User {
  id: number; username: string; role: string; created_at?: string
  /** 商家账号绑定的机构；平台管理员为 null。前端据此决定进哪个端。 */
  client_id?: number | null
}
export interface Credentials { username: string; password: string }
export interface RegisterPayload extends Credentials {
  role?: 'merchant' | 'admin' | 'operator'
  /** 商家注册时用于创建并绑定机构；管理员忽略。 */
  client_name?: string | null
}
export interface Session { access_token: string; token_type: string; user: User }
export const login = (data: Credentials) => request<Session>('POST', '/auth/login', data)
export const register = (data: RegisterPayload) => request<User>('POST', '/auth/register', data)
export const me = () => request<User>('GET', '/auth/me')
