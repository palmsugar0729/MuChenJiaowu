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
  // `/` 不再是「一个页面」，只是落到第一个 tab 上。
  // 底部导航栏（components/TabBar.vue）接管了一级入口，首页那张卡片列表退休了。
  { path: '/', redirect: { name: 'lesson-list' } },
  {
    path: '/me',
    name: 'me',
    component: () => import('@/views/MineView.vue'),
  },
  {
    path: '/contracts',
    name: 'contract-list',
    component: () => import('@/views/ContractListView.vue'),
  },

  // 都放在 catch-all 之前。
  //
  // 注：vue-router 4+ 是按路径「具体程度」打分匹配的，静态段比 :id 优先，
  // 所以 `/classes/new` 就算写在 `/classes/:id` 后面也不会被抢走 ——
  // 这里按可读性排列，不是靠顺序兜正确性。
  {
    path: '/lessons',
    name: 'lesson-list',
    component: () => import('@/views/LessonListView.vue'),
  },
  {
    path: '/lessons/new',
    name: 'lesson-new',
    component: () => import('@/views/LessonFormView.vue'),
  },
  {
    path: '/lessons/:id',
    name: 'lesson-detail',
    component: () => import('@/views/LessonDetailView.vue'),
  },
  {
    path: '/lessons/:id/edit',
    name: 'lesson-edit',
    component: () => import('@/views/LessonFormView.vue'),
  },

  {
    path: '/classes',
    name: 'class-list',
    component: () => import('@/views/ClassListView.vue'),
  },
  {
    path: '/classes/new',
    name: 'class-new',
    component: () => import('@/views/ClassFormView.vue'),
  },
  {
    path: '/classes/:id',
    name: 'class-detail',
    component: () => import('@/views/ClassDetailView.vue'),
  },
  {
    path: '/classes/:id/edit',
    name: 'class-edit',
    component: () => import('@/views/ClassFormView.vue'),
  },
  {
    path: '/students',
    name: 'student-list',
    component: () => import('@/views/StudentListView.vue'),
  },
  {
    path: '/students/new',
    name: 'student-new',
    component: () => import('@/views/StudentFormView.vue'),
  },
  {
    path: '/students/:id',
    name: 'student-detail',
    component: () => import('@/views/StudentDetailView.vue'),
  },
  {
    path: '/students/:id/edit',
    name: 'student-edit',
    component: () => import('@/views/StudentFormView.vue'),
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

  // 已登录、不欠改密：登录页没什么好看的，送回第一个 tab
  if (to.meta.public) return { name: 'lesson-list' }

  // 合同管理**只给管理员**（用户 2026-10-05 定的）。底栏本来就不给老师显示这个 tab，
  // 这里再兜一道 —— 手输 URL 或旧书签也得挡住，不能只靠按钮隐藏。
  if (to.name === 'contract-list' && !auth.isAdmin) return { name: 'lesson-list' }

  return true
})

export default router
