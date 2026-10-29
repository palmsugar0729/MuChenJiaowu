<script setup>
/**
 * ⚠️ **死文件，全仓库没有任何地方引用它了**（路由表里没有，也没有组件 import）。
 *
 * Phase 2W 的「首页卡片列表」在底栏（`TabBar.vue`）上线后就被顶掉了 ——
 * 「我的」页接管了这里最后剩下的那两件事。`/` 现在直接 redirect 到课程页。
 *
 * 留着没删，是因为删文件属于本轮之外的决定（要删就单独提一次，
 * 顺手删掉会让下一次 review 的 diff 里混进一个不相干的决定）。
 * 但里面那句「导出 Excel、审批、月视图课表还在开发中」早就全做完了，
 * 已经不成立，所以先把那句话去掉。
 */
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

      <div class="card home__card">
        <p class="home__greeting">欢迎，{{ auth.displayName }}</p>
        <p class="home__meta">{{ auth.user?.phone }}</p>
      </div>

      <!-- 一级入口。老师和管理员看到的是同一套页面，
           管理员只是在这些页面里多几个按钮（后端也会独立拦） -->
      <div class="list">
        <button
          class="list__item"
          type="button"
          @click="router.push({ name: 'lesson-list' })"
        >
          <p class="list__title">课程</p>
          <p class="list__meta">今天的课、点名、完成上课（扣课时）</p>
        </button>

        <button
          class="list__item"
          type="button"
          @click="router.push({ name: 'class-list' })"
        >
          <p class="list__title">班级</p>
          <p class="list__meta">班级名单、在册学生、费率</p>
        </button>

        <button
          class="list__item"
          type="button"
          @click="router.push({ name: 'student-list' })"
        >
          <p class="list__title">学生</p>
          <p class="list__meta">剩余课时、充值调整、课时流水</p>
        </button>
      </div>

      <div class="toolbar">
        <button class="btn btn--ghost" type="button" @click="logout">退出登录</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 卡片本身没有下边距，原先靠里面那个按钮撑着；现在下面是入口列表，得自己留 */
.home__card {
  margin-bottom: 16px;
}

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
