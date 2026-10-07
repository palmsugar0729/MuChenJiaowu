<script setup>
/**
 * 顶栏：返回键 + 标题 + 右侧操作区。
 *
 * 为什么只抽这一个组件：6 个页面每个都要「返回 + 标题」，这是第 3 处以上重复。
 * 列表行、表单字段**不抽组件**——它们用 CSS 类就够了，而且越抽象，
 * 将来移植 uniapp 时越要整个重写（div→view 的映射都藏在组件里）。
 */

import { useRouter } from 'vue-router'

const props = defineProps({
  title: { type: String, default: '' },
  /** 没有上一页时退到哪（直接输 URL 进来的场景）。 */
  to: { type: String, default: '/' },
  /**
   * 要不要显示返回键。
   *
   * ⚠️ **一级页面（底栏那 5 个 tab）必须传 `false`**：它们没有「上一页」，
   *    返回键要么把人送去一个莫名其妙的地方，要么原地不动 —— 两种都像坏了。
   *    二级页（详情 / 表单）保持默认的 true。
   */
  back: { type: Boolean, default: true },
})

const router = useRouter()

function goBack() {
  // ⚠️ 直接输 URL 进来时 history 里没有上一页，router.back() 会把人留在原地 ——
  // 看着像「按钮坏了」。vue-router 在 history.state.back 里记了自己有没有上一页。
  if (window.history.state?.back) router.back()
  else router.replace(props.to)
}
</script>

<template>
  <header class="app-header">
    <button
      v-if="back"
      class="app-header__back"
      type="button"
      aria-label="返回"
      @click="goBack"
    >
      ‹
    </button>

    <h1 class="app-header__title" :class="{ 'app-header__title--noback': !back }">
      {{ title }}
    </h1>

    <!-- 右侧留给操作按钮（编辑 / 删除），没有就不占位 -->
    <div class="app-header__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.app-header__back {
  flex: none;
  width: var(--tap-min);
  height: var(--tap-min);
  padding: 0;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text);
  font-size: 28px;
  line-height: 1;
  cursor: pointer;
}

.app-header__back:active {
  background: var(--color-primary-light);
}

.app-header__title {
  flex: 1;
  margin: 0;
  /* 返回键是 44px 的触控区，但视觉上不该把标题推得那么右 —— 负边距抵掉一点 */
  margin-left: -4px;
  font-size: 18px;
  font-weight: 600;
  /* 班级名 / 学生名可能很长，别把右侧按钮挤出去 */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 没有返回键时那个负边距就没意义了，会把标题拉到贴着卡片边 */
.app-header__title--noback {
  margin-left: 0;
}

.app-header__actions {
  flex: none;
  display: flex;
  gap: 8px;
}
</style>
