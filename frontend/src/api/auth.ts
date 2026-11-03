import { request } from './http'
export interface User { id: number; username: string; role: string; created_at?: string }
export interface Credentials { username: string; password: string }
export interface Session { access_token: string; token_type: string; user: User }
export const login = (data: Credentials) => request<Session>('POST', '/auth/login', data)
export const register = (data: Credentials) => request<User>('POST', '/auth/register', data)
export const me = () => request<User>('GET', '/auth/me')
