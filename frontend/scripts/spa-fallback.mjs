/**
 * GitHub Pages SPA 深路径物理兜底。
 *
 * 背景：本项目用 vue-router history 模式 + 尾斜杠（/tools/safekeep/）。
 * GitHub Pages 只认识仓库里真实存在的静态文件，深路径刷新会落到 404.html。
 * 而本项目前面还有一层 CDN（阿里云 ESA）：
 *   - /admin/apps/ 命中新站点的 404.html，靠 sessionStorage + JS 跳首页恢复；
 *   - /tools/* 前缀走另一条回源规则，连我们的 404.html 都拿不到，直接 GitHub
 *     原生「Site not found」，用户看到 404。
 * 两套机制都不可靠（CDN 缓存旧 bundle、跨源 sessionStorage 丢失等）。
 *
 * 解法：构建后把 dist/index.html 复制成每个已知静态路由目录下的 index.html，
 * 并让 404.html 直接等于 index.html。这样任意深路径直达时，Pages 返回的就是
 * 完整 SPA 入口，vue-router 按 location.pathname 直接渲染对应页面，不依赖任何
 * JS 跳转或 sessionStorage，也不受 CDN 缓存旧 bundle 影响。
 *
 * 动态路由（/apps/:code/、/resumes/:user_id/）无法穷举，仍走 404.html 兜底，
 * 但此时 404.html = index.html，同样能直接渲染。
 */
import { cpSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const dist = join(root, 'dist')
const indexHtml = join(dist, 'index.html')

if (!existsSync(indexHtml)) {
  console.error('[spa-fallback] dist/index.html 不存在，请先执行 vite build')
  process.exit(1)
}

/** 已知静态路由（与 src/router/index.ts 保持一致；动态路由不在此列） */
const STATIC_ROUTES = [
  '/home/',
  '/apps-home/',
  '/products/',
  '/products/superset/',
  '/admin/apps/',
  '/tools/safekeep/',
  '/tools-home/',
  '/wedesk/',
  '/zaima/',
  '/privacy/',
  '/terms/',
  '/test/',
  '/login/',
]

for (const route of STATIC_ROUTES) {
  const target = join(dist, route, 'index.html')
  mkdirSync(dirname(target), { recursive: true })
  cpSync(indexHtml, target)
}

// 404.html 直接等于 index.html：动态路由与任何未知路径都交给 SPA 自己处理
writeFileSync(join(dist, '404.html'), readFileSync(indexHtml))

console.log(`[spa-fallback] 已生成 ${STATIC_ROUTES.length} 个深路径入口 + 404.html = index.html`)
