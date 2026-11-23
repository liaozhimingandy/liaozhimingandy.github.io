import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// 别名必须与 tsconfig.app.json 的 baseUrl+paths 保持一致，否则 @/ 导入会退化成 any
export default defineConfig({
  // 部署在自定义域根路径（www.alsoapp.com，GitHub Pages 用户站点 + CNAME），故 base=/。
  // 后端（FastAPI）托管 dist 时用 VITE_PUBLIC_PATH=/ap/ 覆盖，与 AP_PUBLIC_PATH 保持一致。
  // 所有静态资源 JS/CSS 会内联此前缀，保证对应部署形态下能正确加载。
  base: process.env.VITE_PUBLIC_PATH || '/',
  // tailwindcss() 走 Vite 原生插件（Tailwind v4，无需 postcss.config / tailwind.config）
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    // 产物交给 FastAPI 托管；关闭 sourcemap 避免泄漏源码路径
    outDir: 'dist',
    sourcemap: false,
  },
})
