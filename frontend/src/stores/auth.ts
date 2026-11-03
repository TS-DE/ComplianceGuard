import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as api from '../api/auth'
import { resetUnauthorized } from '../api/http'
export const useAuth = defineStore('auth', () => {
  const user = ref<api.User | null>(null)
  async function signIn(credentials: api.Credentials) {
    const session = await api.login(credentials)
    localStorage.setItem('token', session.access_token)
    user.value = session.user
    resetUnauthorized()
  }
  async function restore() { user.value = await api.me() }
  function logout() { localStorage.removeItem('token'); user.value = null }
  window.addEventListener('auth-expired', logout)
  return { user, signIn, restore, logout }
})
