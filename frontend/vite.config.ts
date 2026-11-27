import { fileURLToPath, URL } from 'node:url'
import { execSync } from 'node:child_process'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// 构建版本信息（官网页脚展示）：git 不可用时降级，不阻塞构建
let commitHash = 'unknown'
try {
  commitHash = execSync('git rev-parse --short HEAD', { cwd: fileURLToPath(new URL('.', import.meta.url)) })
    .toString().trim()
} catch { /* 非 git 环境 */ }
const appVersion = '1.0.0'

// 别名必须与 tsconfig.app.json 的 baseUrl+paths 保持一致，否则 @/ 导入会退化成 any
export default defineConfig({
  // 部署在自定义域根路径（www.alsoapp.com，GitHub Pages 用户站点 + CNAME），故 base=/。
  // 后端（FastAPI）托管 dist 时用 VITE_PUBLIC_PATH=/ap/ 覆盖，与 AP_PUBLIC_PATH 保持一致。
  // 所有静态资源 JS/CSS 会内联此前缀，保证对应部署形态下能正确加载。
  base: process.env.VITE_PUBLIC_PATH || '/',
  // tailwindcss() 走 Vite 原生插件（Tailwind v4，无需 postcss.config / tailwind.config）
  plugins: [vue(), tailwindcss()],
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
    __COMMIT_HASH__: JSON.stringify(commitHash),
  },
  // 本地开发：Vite dev server（热更新，无需构建）+ /v1 反向代理到本地后端。
  // 后端地址可用 AP_DEV_API 覆盖（默认 127.0.0.1:8081）；同源代理避免 CORS，
  // 前端 fetch('/v1/...') 与生产「后端托管 dist」形态完全一致。
  server: {
    port: 5174,
    proxy: {
      '/v1': {
        target: process.env.AP_DEV_API || 'http://127.0.0.1:8002',
        changeOrigin: true,
      },
      // 文章封面/正文配图（采集图片静态目录，后端 /images 挂载）
      '/images': {
        target: process.env.AP_DEV_API || 'http://127.0.0.1:8002',
        changeOrigin: true,
      },
    },
  },
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
