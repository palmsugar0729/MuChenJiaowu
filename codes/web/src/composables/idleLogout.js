/**
 * 无操作自动登出（用户 2026-11-26 定的：**60 分钟**）。
 *
 * 为什么放在前端：这是个「人走开了、手机还亮着」的场景，风险来自**屏幕上的会话**，
 * 不是来自 token 能活多久。前端踢回登录页就够用，不用为它加一套服务端会话表。
 *
 * ⚠️ 手机浏览器后台会**限制定时器**，所以除了 `setInterval` 兜着，还得在
 *    `visibilitychange`（切回前台）时立刻对一次表 —— 否则锁屏两小时回来，
 *    计时器还没跑够那一轮，人就直接接着用了。
 * ⚠️ 只挂一次：在 `App.vue` 里调用（跟 `AppDialog` 一个思路），别每个页面各挂一个。
 * ⚠️ 跳登录页时带 `?idle=1`，登录页据此显示「超过 60 分钟没有操作，已自动退出登录」——
 *    不然用户会以为是自己被踢了或者系统坏了。
 */
import { onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

/** 多久没操作就登出。改这里 = 改全系统。 */
const IDLE_MS = 60 * 60 * 1000

/** 多久对一次表。30 秒足够，别刷 DOM。 */
const CHECK_MS = 30 * 1000

/**
 * 哪些算「操作」：点、键盘、滚动、触摸都算。
 * ⚠️ 不用 `mousemove` —— 它太密，而且人只是动了动鼠标没在操作；
 *    滚动算，因为看列表确实得滑。
 */
const ACTIVITY_EVENTS = ['pointerdown', 'keydown', 'touchstart', 'scroll', 'wheel']

export function useIdleLogout() {
  const auth = useAuthStore()
  const router = useRouter()

  let lastActive = Date.now()
  let timer = null

  function touch() {
    lastActive = Date.now()
  }

  function check() {
    // 没登录就没什么可登出的（登录页停留两小时也照样能用）
    if (!auth.isAuthenticated) {
      lastActive = Date.now()
      return
    }
    if (Date.now() - lastActive < IDLE_MS) return

    auth.logout()
    // replace 而不是 push：登出后不该能「后退」回到刚才那页
    router.replace({ name: 'login', query: { idle: '1' } })
    lastActive = Date.now()
  }

  /** 切回前台立刻对一次表 —— 后台期间定时器可能根本没跑 */
  function onVisibility() {
    if (document.visibilityState === 'visible') check()
  }

  onMounted(() => {
    for (const name of ACTIVITY_EVENTS) {
      // passive：滚动是高频事件，别让监听器拖慢页面
      window.addEventListener(name, touch, { passive: true })
    }
    document.addEventListener('visibilitychange', onVisibility)
    timer = window.setInterval(check, CHECK_MS)
  })

  onBeforeUnmount(() => {
    for (const name of ACTIVITY_EVENTS) {
      window.removeEventListener(name, touch)
    }
    document.removeEventListener('visibilitychange', onVisibility)
    if (timer !== null) window.clearInterval(timer)
  })
}
