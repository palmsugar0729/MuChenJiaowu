import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/change-password',
    name: 'change-password',
    component: () => import('@/views/ChangePasswordView.vue'),
  },
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
  },
  // 认不出的地址一律回首页，再由下面的守卫决定是放行还是改道
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// ⚠️ Vue Router 5 起弃用了守卫里的 next() 回调，一律用返回值：
//    return true            -> 放行
//    return { name: 'xxx' } -> 改道
router.beforeEach(async (to) => {
  const auth = useAuthStore()

  // 刷新页面后 store 是空的，先把用户信息补回来再判断
  await auth.ensureLoaded()

  // 没登录：只放行登录页，其余挡回登录页并记住原目标
  if (!auth.isAuthenticated) {
    if (to.meta.public) return true
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  // 已登录但欠一次改密：除了改密页，去哪儿都给你改道
  // （后端不拦这件事，它纯粹是界面上的强制 —— 见 routers/auth.py 的注释）
  if (auth.mustChangePassword) {
    return to.name === 'change-password' ? true : { name: 'change-password' }
  }

  // 已登录、不欠改密：登录页没什么好看的
  if (to.meta.public) return { name: 'home' }

  return true
})

export default router
