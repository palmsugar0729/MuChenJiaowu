<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const ROLE_LABELS = {
  super_admin: '超级管理员',
  admin: '管理员',
  teacher: '老师',
}

const roleLabel = computed(() => ROLE_LABELS[auth.user?.role] || auth.user?.role || '')

function logout() {
  auth.logout()
  router.replace({ name: 'login' })
}
</script>

<template>
  <div class="page">
    <div class="page__inner">
      <div class="brand">
        <h1 class="brand__title">沐晨课程管理</h1>
        <p class="brand__sub">{{ roleLabel }}</p>
      </div>

      <div class="card">
        <p class="home__greeting">欢迎，{{ auth.displayName }}</p>
        <p class="home__meta">{{ auth.user?.phone }}</p>

        <button class="btn btn--ghost" type="button" @click="logout">退出登录</button>
      </div>

      <p class="hint">课程表、考勤等功能还在开发中</p>
    </div>
  </div>
</template>

<style scoped>
.home__greeting {
  margin: 0 0 4px;
  font-size: 18px;
  font-weight: 600;
}

.home__meta {
  margin: 0 0 20px;
  font-size: 14px;
  color: var(--color-text-muted);
}
</style>
