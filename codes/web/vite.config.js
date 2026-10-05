import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// dev 和 preview 共用一份代理。
//
// 前端代码里永远只写相对的 /api：dev 靠这里转发到本机后端，生产靠 Nginx 反代。
// 一份代码两处跑，不需要环境变量切换 baseURL。
//
// target 写 127.0.0.1 是对的 —— 手机访问 http://192.168.x.x:5173 时，
// 是**这台 PC 上的 Vite 进程**去连本机 8000，手机压根不解析这个地址。
const proxy = {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
    // 不加 rewrite：后端路由本身就在 /api 前缀下（settings.api_prefix），原样转发
  },
}

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    // ★ 必须绑 0.0.0.0。Vite 默认只听 localhost，手机连不上 —— 第一坑。
    host: true,
    port: 5173,
    // 端口被占直接报错，别悄悄换端口：换了手机书签就失效，排查半天
    strictPort: true,
    proxy,
  },
  // 让手机也能验收**构建产物**（vite preview），同样走代理
  preview: {
    host: true,
    port: 4173,
    proxy,
  },
})
