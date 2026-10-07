<script setup>
/**
 * 「我的」—— 账号信息 + 退出登录。
 *
 * 原来这里是 HomeView（首页卡片列表）。加了底部导航栏之后，
 * 一级入口由 TabBar 接管，这个页面就只剩「当前登录的是谁」和收尾操作了。
 * 路由名从 `home` 改成 `me`，路径 `/me`。
 */

import { computed } from 'vue'
import { useRouter } from 'vue-router'

import AppHeader from '@/components/AppHeader.vue'
import TabBar from '@/components/TabBar.vue'
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
  <div class="page page--top page--tabbed">
    <div class="page__inner">
      <!-- 一级页面，没有「上一页」可退 -->
      <AppHeader title="我的" :back="false" />

      <div class="card">
        <p class="mine__name">{{ auth.displayName }}</p>
        <p class="mine__meta">{{ auth.user?.phone }} · {{ roleLabel }}</p>
      </div>

      <div class="toolbar">
        <button
          class="btn btn--ghost"
          type="button"
          @click="router.push({ name: 'change-password' })"
        >
          修改密码
        </button>
      </div>

      <div class="toolbar">
        <button class="btn btn--ghost" type="button" @click="logout">退出登录</button>
      </div>

      <p class="hint">导出 Excel、审批、月视图课表还在开发中</p>
    </div>

    <TabBar />
  </div>
</template>

<style scoped>
.mine__name {
  margin: 0 0 4px;
  font-size: 18px;
  font-weight: 600;
}

.mine__meta {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-muted);
}
</style>
