/**
 * 生产部署默认值静态守卫（node --test，纯文本断言，无浏览器）。
 *
 * 回归背景（2026-11-12）：公网入口 `https://www.alsoapp.com/tools/#/safekeep`
 * 看不到「登录并从云端恢复」，排查出三层与仓库配置直接相关的问题：
 *   1) 生产回调/登出地址内联的是 `liaozhimingandy.github.io`，而实际访问域是
 *      自定义域 `www.alsoapp.com`（前者会 301 到后者）。跨 origin 会让
 *      sessionStorage 里的「恢复意图」丢失，且该 URI 未在 Logto 登记（400）。
 *   2) 后端 CORS 白名单填的是 Pages 源站，浏览器实际 origin 是自定义域。
 *   3) 自定义域 CDN 把 HTML 缓存 30 天，Actions 部署成功但公网仍是旧版。
 *
 * 2026-11-23 AP 整合：统一站点迁移到自定义域根路径部署（base=/，不再有 /tools/
 * 前缀），API 根改为 https://api.alsoapp.com，镜像名 fastapi-ap，后端变量前缀
 * TOOLS_* → AP_*。本测试守住仓库能控制的部分；CDN / DNS / Logto 白名单属于
 * 外部控制台配置，需人工验证。
 *
 * 2026-11-24 配置收敛：同一份 VITE_* 曾同时写在 .env.production、GitHub Variables
 * 和代码默认值三处，改一处漏两处。现收敛为：生产文件显式声明必须项（API 根 +
 * Logto endpoint/appId），src/config.ts 的同值默认值仅作兜底，回调由 origin 推导；
 * 工作流不注入任何 VITE_*。
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(fileURLToPath(new URL('../..', import.meta.url)))

function read(rel: string): string {
  return readFileSync(resolve(ROOT, rel), 'utf8')
}

const PROD_ORIGIN = 'https://www.alsoapp.com'
const PROD_CALLBACK = 'https://www.alsoapp.com/'
const PROD_API = 'https://api.alsoapp.com'

test('.env.production 显式声明必须项，可推导项不重复配置', () => {
  const env = read('frontend/.env.production')
  const active = env.split('\n')
    .filter((l) => l.trim() && !l.trimStart().startsWith('#'))
    .map((l) => l.trim())
    .sort()
  assert.deepEqual(active, [
    `VITE_API_BASE_URL=${PROD_API}`,
    'VITE_LOGTO_ENDPOINT=https://account.alsoapp.com',
    'VITE_LOGTO_APP_ID=plu65e7c0nypndqg7s4hp',
  ].sort(), '必须项缺失或出现多余配置')
  assert.doesNotMatch(env, /VITE_DEV_USER_SUB\s*=/, '生产构建不得注入本地联调身份')
  assert.doesNotMatch(env, /VITE_LOGTO_(?:POST_LOGOUT_)?REDIRECT_URI\s*=/, '回调由 origin 推导，不写死域名')
  assert.doesNotMatch(env, /https:\/\/liaozhimingandy\.github\.io\//, '不能再用 Pages 源站')
  assert.doesNotMatch(env, /www\.alsoapp\.com\/tools\//, '不应残留 /tools/ 前缀')
  assert.equal(PROD_CALLBACK.includes('#'), false, 'OAuth redirect_uri 不能带 fragment')
})

test('必须项在 env 与代码默认两处保持一致，回调仍由 origin 推导', () => {
  const env = read('frontend/.env.production')
  assert.match(env, /^VITE_API_BASE_URL=https:\/\/api\.alsoapp\.com$/m)
  assert.match(env, /^VITE_LOGTO_ENDPOINT=https:\/\/account\.alsoapp\.com$/m)
  assert.match(env, /^VITE_LOGTO_APP_ID=plu65e7c0nypndqg7s4hp$/m)
  const config = read('frontend/src/config.ts')
  assert.match(config, /DEFAULT_LOGTO_ENDPOINT\s*=\s*'https:\/\/account\.alsoapp\.com'/)
  assert.match(config, /DEFAULT_LOGTO_APP_ID\s*=\s*'plu65e7c0nypndqg7s4hp'/)
  // 根路径部署时 new URL(BASE_URL, origin) => https://www.alsoapp.com/
  assert.match(config, /new URL\(publicBase, origin\)/)
  assert.equal(PROD_API.startsWith('https://'), true)
  assert.equal(PROD_ORIGIN.startsWith('https://'), true)
})

test('部署工作流不注入任何 VITE_*，构建只读 .env.production', () => {
  // 只看实际配置行，忽略注释中的说明文字
  const wf = read('.github/workflows/deploy-github-pages.yml')
    .split('\n').filter((l) => !l.trimStart().startsWith('#')).join('\n')

  assert.doesNotMatch(wf, /VITE_[A-Z0-9_]+/, '工作流不得出现 VITE_*（含 vars 透传与 env 块）')
  assert.doesNotMatch(wf, /\|\|\s*['"]https?:/, '不得内联具体地址作默认值')
  assert.doesNotMatch(wf, /printenv/, '不再需要 vars 空值回退逻辑')
  assert.match(wf, /run: npm run build/)
})

test('后端 CORS 白名单填前端 origin，不是后端域名', () => {
  const env = read('backend/.env.example')
  assert.match(env, /^AP_CORS_ORIGINS=https:\/\/www\.alsoapp\.com$/m)
  assert.doesNotMatch(env, /^AP_CORS_ORIGINS=.*api\.alsoapp\.com/m)
  assert.equal(PROD_ORIGIN.endsWith('/'), false, 'CORS origin 不带尾斜杠')
})

test('后端镜像名固定为 fastapi-ap', () => {
  const wf = read('.github/workflows/build-images.yml')
  assert.match(wf, /^\s*IMAGE_NAME: fastapi-ap$/m)
  assert.doesNotMatch(wf, /fastapi-tools|tools-backend/)
  for (const f of ['backend/.env.example']) {
    assert.match(read(f), /fastapi-ap/, `${f} 未同步新镜像名`)
  }
  // docker-compose.yml 走 build: 本地构建，不引用镜像名，只断言不残留旧名
  assert.doesNotMatch(read('backend/docker-compose.yml'), /fastapi-tools/)
})

test('部署作业输出 CDN cache-buster 验证地址（history 路径，无 #）', () => {
  const wf = read('.github/workflows/deploy-github-pages.yml')
  assert.match(wf, /公网验证地址（绕过 CDN 缓存）/)
  assert.match(wf, /https:\/\/www\.alsoapp\.com\/\?v=\$\{TS\}/)
  assert.doesNotMatch(wf, /\?v=\$\{TS\}#/)
})

test('构建后 cp index.html 为 404.html（history 深路径兜底，源码不维护 404）', () => {
  const wf = read('.github/workflows/deploy-github-pages.yml')
  assert.match(wf, /working-directory: frontend\/dist\n\s+run: cp index\.html 404\.html/)
  assert.doesNotMatch(wf, /spa-fallback/)
  const pkg = JSON.parse(read('frontend/package.json'))
  assert.doesNotMatch(pkg.scripts.build, /spa-fallback/)
})

test('前端工作流按实际 diff 跳过：未改 frontend/** 不构建不部署', () => {
  const wf = read('.github/workflows/deploy-github-pages.yml')
  assert.match(wf, /^\s+changes:\n/m, '缺少 changes 作业')
  assert.match(wf, /frontend: \$\{\{ steps\.check\.outputs\.frontend \}\}/, 'changes 需输出 frontend 判定')
  assert.match(wf, /git diff --name-only/, '必须用真实 diff 而非只看触发路径')
  assert.match(wf, /grep -q '\^frontend\/'/, '判定前缀必须是 frontend/')
  assert.match(wf, /needs: changes\n\s+if: needs\.changes\.outputs\.frontend == 'true'/, 'build 必须被门禁')
  assert.match(wf, /needs: \[changes, build\]\n\s+if: needs\.changes\.outputs\.frontend == 'true'/, 'deploy 必须被门禁')
  assert.match(wf, /\[ "\$\{EVENT_NAME\}" = "workflow_dispatch" \]/, '手动触发需绕过 diff 门禁，便于验证工作流')
})

test('后端镜像工作流按实际 diff 跳过：未改 backend/** 不构建不推镜像', () => {
  const wf = read('.github/workflows/build-images.yml')
  assert.match(wf, /^\s+changes:\n/m, '缺少 changes 作业')
  assert.match(wf, /backend: \$\{\{ steps\.check\.outputs\.backend \}\}/, 'changes 需输出 backend 判定')
  assert.match(wf, /git diff --name-only/, '必须用真实 diff 而非只看触发路径')
  assert.match(wf, /grep -q '\^backend\/'/, '判定前缀必须是 backend/')
  assert.match(wf, /meta:\n(?:\s+.*\n){0,4}\s+needs: changes\n\s+if: needs\.changes\.outputs\.backend == 'true'/, 'meta 必须被门禁')
  assert.match(wf, /needs: \[changes, meta\]\n\s+if: needs\.changes\.outputs\.backend == 'true'/, 'build 必须被门禁')
  assert.match(wf, /needs: \[changes, meta, build\]\n\s+if: needs\.changes\.outputs\.backend == 'true'/, 'verify 必须被门禁')
  assert.match(wf, /if: always\(\) && needs\.changes\.outputs\.backend == 'true'/, '无后端变更时报告也不该刷屏')
  assert.match(wf, /\[ "\$\{EVENT_NAME\}" = "workflow_dispatch" \]/, '手动触发需绕过 diff 门禁，便于验证工作流')
})
