import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { setTokenGetter, setUnauthorizedHandler } from './api/client'
import { useAuthStore } from './stores/auth'

import './styles/variables.css'
import './styles/base.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)

// client 不认识 store，也不认识 router（那会形成循环依赖，还会把 web 独有的
// 路由拖进本该可移植的网络层）。所以在这里反向接线 —— client 只认两个回调。
setTokenGetter(() => useAuthStore().token)

setUnauthorizedHandler(() => {
  useAuthStore().logout()

  // 已经在登录页就别再跳了（守卫里也会兜底挡一次）
  if (router.currentRoute.value.name !== 'login') {
    router.replace({ name: 'login' }).catch(() => {})
  }
})

app.mount('#app')
