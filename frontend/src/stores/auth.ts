import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') ?? '')
  const username = ref(localStorage.getItem('username') ?? '未登录')
  const role = ref(localStorage.getItem('role') ?? '')

  function setToken(t: string) {
    token.value = t
    localStorage.setItem('token', t)
  }

  function setUser(name: string, r: string) {
    username.value = name || '未登录'
    role.value = r ?? ''
    localStorage.setItem('username', username.value)
    localStorage.setItem('role', role.value)
  }

  /** 有 token 但缺用户名（如老版本登录过）时，从 /auth/me 补全 */
  async function hydrate() {
    if (!token.value || username.value !== '未登录') return
    try {
      const { api } = await import('../api/client')
      const me = await api.me()
      setUser(me.username, me.role)
    } catch { /* token 失效则保持未登录 */ }
  }

  function logout() {
    token.value = ''
    username.value = '未登录'
    role.value = ''
    localStorage.clear()
  }

  return { token, username, role, setToken, setUser, hydrate, logout }
})
