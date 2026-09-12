import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') ?? '')
  const username = ref(localStorage.getItem('username') ?? '未登录')
  const role = ref(localStorage.getItem('role') ?? '')

  function setToken(t: string) {
    token.value = t
    localStorage.setItem('token', t)
    try {
      const payload = JSON.parse(atob(t.split('.')[1]))
      role.value = payload.role ?? ''
      localStorage.setItem('role', role.value)
    } catch { /* ignore */ }
  }

  function logout() {
    token.value = ''
    localStorage.clear()
  }

  return { token, username, role, setToken, logout }
})
