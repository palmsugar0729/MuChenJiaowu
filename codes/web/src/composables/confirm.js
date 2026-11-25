/**
 * 应用内确认框 —— 取代 `window.confirm`。
 *
 * ★ 为什么要自建（用户 2026-11-25 定的）：
 *   1. **微信小程序里没有 `window`**，uniapp 那边只能用 `uni.showModal`，
 *      现在这 8 个调用点到时候全要重写；
 *   2. 这个组件是普通 DOM + Vue 模板，搬到 uniapp 基本能原样用；
 *   3. 浏览器原生那个白框跟现在的界面完全不是一个风格。
 *
 * 用法（和 `window.confirm` 几乎一样，只是要 `await`）：
 *
 *     import { confirmAction } from '@/composables/confirm'
 *     if (!(await confirmAction({ message: '把「张三」移出这个班？' }))) return
 *
 * ⚠️ 弹框本体挂在 `App.vue`（全局只有一份），所以任何页面都能调，
 *   不需要在模板里摆一个 `<AppDialog>`。
 */
import { reactive } from 'vue'

/** 当前这一句弹框的状态。`App.vue` 直接绑它。 */
export const dialogState = reactive({
  open: false,
  title: '确认',
  message: '',
  confirmText: '确定',
  cancelText: '取消',
  danger: false,
})

/** 等待中的那个 Promise 的 resolve —— 同一时刻只可能有一句在等。 */
let pendingResolve = null

/**
 * 弹一句确认，等用户点。
 * @returns {Promise<boolean>} 点确定是 true，点取消 / 点遮罩是 false
 */
export function confirmAction({
  title = '确认',
  message = '',
  confirmText = '确定',
  cancelText = '取消',
  danger = false,
} = {}) {
  // 上一句还没答就又要弹：把上一句当成「取消」结束掉。
  // 不这么做的话它的 Promise 永远悬着，调用方的 await 就再也不继续了。
  if (pendingResolve) {
    pendingResolve(false)
    pendingResolve = null
  }

  Object.assign(dialogState, {
    open: true,
    title,
    message,
    confirmText,
    cancelText,
    danger,
  })

  return new Promise((resolve) => {
    pendingResolve = resolve
  })
}

/** 用户点了「确定 / 取消 / 遮罩」。只由 App.vue 调。 */
export function answerDialog(ok) {
  dialogState.open = false
  const resolve = pendingResolve
  pendingResolve = null
  if (resolve) resolve(ok)
}
