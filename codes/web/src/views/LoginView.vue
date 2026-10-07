<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PasswordField from '@/components/PasswordField.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const phone = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

/** ?redirect= 只接受站内路径，别的一律回首页（防开放重定向）。 */
function safeRedirect(value) {
  return typeof value === 'string' && value.startsWith('/') ? value : '/'
}

async function submit() {
  error.value = ''

  if (!phone.value.trim() || !password.value) {
    error.value = '请填写手机号和密码'
    return
  }

  loading.value = true
  try {
    const user = await auth.login(phone.value.trim(), password.value)

    // 首次登录必须先改密，否则回原目标（守卫也会再兜一次）
    router.replace(
      user.must_change_password
        ? { name: 'change-password' }
        : safeRedirect(route.query.redirect),
    )
  } catch (e) {
    // 后端的 detail 已经写好文案了（「手机号或密码不正确」/「账号已停用…」），直接显示
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page">
    <div class="page__inner">
      <div class="brand">
        <h1 class="brand__title">沐晨课程管理</h1>
        <p class="brand__sub">请使用手机号登录</p>
      </div>

      <form class="card" @submit.prevent="submit">
        <p v-if="error" class="alert">{{ error }}</p>

        <div class="field">
          <label class="field__label" for="phone">手机号</label>
          <input
            id="phone"
            v-model="phone"
            class="field__input"
            type="tel"
            inputmode="numeric"
            autocomplete="username"
            placeholder="请输入手机号"
          />
        </div>

        <PasswordField
          id="password"
          v-model="password"
          label="密码"
          autocomplete="current-password"
          placeholder="请输入密码"
        />

        <button class="btn" type="submit" :disabled="loading">
          {{ loading ? '登录中…' : '登录' }}
        </button>
      </form>
    </div>
  </div>
</template>
