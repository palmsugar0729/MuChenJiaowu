<script setup>
/**
 * 底部导航栏。
 *
 * 抽成组件是因为它出现在**每个一级页面**上，跟 AppHeader 一个理由；
 * 而且里面有一点真逻辑（按角色过滤、按路由判高亮）。
 *
 * ⚠️ 「合同」**只给管理员看**（用户 2026-10-05 定的）。所以 tab 数量是**可变的**：
 *    老师 4 个、管理员 5 个。用 flex 均分，别写死宽度。
 *
 * ⚠️ 这里**不**用 `router-link`，用 `<button>` + `router.push`：
 *    高亮判断要精确到「哪个 tab」，而 `router-link-active` 是前缀匹配 ——
 *    `/lessons` 会把它下面的 `/lessons/123` 也算成激活，行为不好猜。
 */

import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

/** 一级入口。`isAdmin` 已含超管（见 stores/auth.js）。 */
const tabs = computed(() =>
  [
    { name: 'lesson-list', label: '课程' },
    { name: 'class-list', label: '班级' },
    { name: 'student-list', label: '学生' },
    { name: 'contract-list', label: '合同', adminOnly: true },
    { name: 'me', label: '我的' },
  ].filter((tab) => !tab.adminOnly || auth.isAdmin),
)

/**
 * 高亮哪个 tab。
 *
 * ⚠️ 不能只比 `route.name`：详情页的名字是 `lesson-detail`，
 *    那属于「课程」这个 tab，只比名字的话进详情底栏就全灭了。
 *    所以比的是**路由名字的前缀**。
 */
function isActive(tab) {
  const current = route.name
  if (typeof current !== 'string') return false
  // 把 `-list` / `-detail` / `-new` / `-edit` 这类后缀剥掉再比
  return current.startsWith(tab.name.replace(/-list$/, ''))
}

function go(tab) {
  if (route.name === tab.name) return
  router.push({ name: tab.name })
}
</script>

<template>
  <nav class="tabbar">
    <button
      v-for="tab in tabs"
      :key="tab.name"
      class="tabbar__btn"
      :class="{ 'tabbar__btn--on': isActive(tab) }"
      type="button"
      :aria-current="isActive(tab) ? 'page' : undefined"
      @click="go(tab)"
    >
      {{ tab.label }}
    </button>
  </nav>
</template>

<style scoped>
/* 固定在底部。z-index 只是为了让长页面滚上来时盖住内容，
   不跟别的东西抢层（这边没有弹窗组件） */
.tabbar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 10;
  display: flex;
  background: var(--color-surface);
  border-top: 1px solid var(--color-border);
  /* 全面屏底部那条横线要躲开，否则按钮被系统手势区压住 */
  padding-bottom: env(safe-area-inset-bottom);
}

.tabbar__btn {
  /* 等分：tabs 数量会变（老师 4 个 / 管理员 5 个），不能写死宽度 */
  flex: 1;
  /* 触控目标 ≥44px */
  min-height: var(--tap-min);
  padding: 8px 4px;
  border: none;
  background: none;
  color: var(--color-text-muted);
  font-size: 13px;
  cursor: pointer;
}

.tabbar__btn--on {
  color: var(--color-primary-dark);
  font-weight: 600;
}

.tabbar__btn:active {
  background: var(--color-primary-light);
}

@media (hover: hover) {
  .tabbar__btn:hover {
    background: var(--color-primary-light);
  }
}
</style>
