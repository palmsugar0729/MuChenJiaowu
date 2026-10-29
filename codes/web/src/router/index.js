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
  // 我的改期申请（老师）。★ 名字以 `me` 开头 → TabBar 点亮「我的」。
  // ⚠️ 别叫 `mine-approval-list`：`mine` 跟 tab 名 `me` 不是前缀关系，
  //    会**五个 tab 全灭**（TabBar.isActive 是 startsWith 匹配）。
  // 路径挂 /me 下，跟「我的」这个入口在一起。
  {
    path: '/me/approvals',
    name: 'me-approval-list',
    component: () => import('@/views/MyApprovalListView.vue'),
  },
  {
    path: '/contracts',
    name: 'contract-list',
    component: () => import('@/views/ContractListView.vue'),
    meta: { adminOnly: true },
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
  // 月视图。名字也以 `lesson` 开头 —— TabBar 的 isActive 按前缀点亮「课程」tab。
  // 静态段 `/month` 比 `/lessons/:id` 优先（同 `/classes/new`）。
  {
    path: '/lessons/month',
    name: 'lesson-month',
    component: () => import('@/views/LessonMonthView.vue'),
  },
  {
    path: '/lessons/new',
    name: 'lesson-new',
    component: () => import('@/views/LessonFormView.vue'),
  },
  // 审批待办（管理员）。★ 名字**故意**叫 `lesson-approval-list`：TabBar.isActive
  // 是剥掉 `-list` 后按前缀点亮 tab 的，名字以 `lesson` 开头才点亮「课程」tab。
  // 叫 `approval-list` 会**五个 tab 全灭**（`approval` 跟哪个 tab 名都对不上），
  // 用户看着就像页面坏了。路径挂 `/lessons/` 下跟 `/lessons/new` 同一个惯例。
  {
    path: '/lessons/approvals',
    name: 'lesson-approval-list',
    component: () => import('@/views/ApprovalListView.vue'),
    meta: { adminOnly: true },
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

  // 只给管理员的页面（合同管理、审批待办）。底栏 / 按钮本来就不给老师显示，
  // 这里再兜一道 —— 手输 URL 或旧书签也得挡住，不能只靠按钮隐藏。
  //
  // ⚠️ 判据是路由上的 `meta.adminOnly`，**不是硬编码路由名**：原来这里写的是
  //    `to.name === 'contract-list'`，每加一个管理员页面就得回来改一次这行，
  //    漏了就是个静默的权限漏洞。现在跟 `meta.public` 一路，加在路由定义上。
  if (to.meta.adminOnly && !auth.isAdmin) return { name: 'lesson-list' }

  return true
})

export default router
