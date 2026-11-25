<script setup>
/**
 * 应用内确认框（纯展示）。状态和 Promise 在 `composables/confirm.js`，
 * 全局只在 `App.vue` 里挂一次。
 *
 * 换成它的理由见 confirm.js 顶部 —— 一句话：`window.confirm` 在小程序里不存在。
 */
defineProps({
  title: { type: String, default: '确认' },
  message: { type: String, default: '' },
  confirmText: { type: String, default: '确定' },
  cancelText: { type: String, default: '取消' },
  /** 真删、扣课时这类**不可撤销**的动作用红色主按钮 */
  danger: { type: Boolean, default: false },
})

const emit = defineEmits(['confirm', 'cancel'])
</script>

<template>
  <!-- 挂到 body 上：页面里有 `transform` / `overflow` 的祖先都关不住它 -->
  <Teleport to="body">
    <div class="dialog-mask" @click.self="emit('cancel')">
      <div class="dialog" role="dialog" aria-modal="true">
        <p class="dialog__title">{{ title }}</p>
        <!-- 原来的 confirm 文案里用 \n 分行，这里靠 CSS 的 pre-line 保留 -->
        <p class="dialog__message">{{ message }}</p>
        <div class="dialog__actions">
          <button class="btn btn--ghost" type="button" @click="emit('cancel')">
            {{ cancelText }}
          </button>
          <button
            class="btn"
            :class="{ 'btn--danger': danger }"
            type="button"
            @click="emit('confirm')"
          >
            {{ confirmText }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
