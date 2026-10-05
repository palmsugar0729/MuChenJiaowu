/**
 * 认证状态。可移植层 —— Pinia 在 uniapp 里同样能用，这里不碰 DOM。
 */

import { defineStore } from 'pinia'

import { changePassword as apiChangePassword, getMe, login as apiLogin } from '@/api/auth'
import { storage } from '@/utils/storage'

const TOKEN_KEY = 'muchen_token'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    // token 持久化：老师手机上不该关个浏览器就要重登。
    // user 不持久化 —— role 是权限依据，宁可每次启动向后端要一份真实的。
    token: storage.get(TOKEN_KEY) || '',
    user: null,
    loading: false,
  }),

  getters: {
    isAuthenticated: (s) => !!s.token,
    mustChangePassword: (s) => !!s.user?.must_change_password,
    isAdmin: (s) => s.user?.role === 'admin' || s.user?.role === 'super_admin',
    displayName: (s) => s.user?.display_name || '',
  },

  actions: {
    setToken(token) {
      this.token = token || ''
      if (token) storage.set(TOKEN_KEY, token)
      else storage.remove(TOKEN_KEY)
    },

    /** 登录成功后 token 和 user 一起到手，不用再拉一次 /users/me。 */
    async login(phone, password) {
      const data = await apiLogin(phone, password)
      this.setToken(data.access_token)
      this.user = data.user
      return data.user
    },

    /**
     * 有 token 但还没有 user 时（典型场景：刷新页面）补拉一次。
     * 拉不到说明 token 已失效或账号被停用 —— 直接登出。
     */
    async ensureLoaded() {
      if (!this.token || this.user || this.loading) return

      this.loading = true
      try {
        this.user = await getMe()
      } catch {
        this.logout()
      } finally {
        this.loading = false
      }
    },

    async changePassword(oldPassword, newPassword) {
      await apiChangePassword(oldPassword, newPassword)

      // 后端只回 {message}，不回 user。本地手动清掉这个标记，
      // 否则路由守卫会一直把你摁在改密页。
      if (this.user) this.user.must_change_password = false
    },

    logout() {
      this.setToken('')
      this.user = null
    },
  },
})
