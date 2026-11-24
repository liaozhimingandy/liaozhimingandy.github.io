import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

/**
 * Also Apps 统一站点路由表 = 官网 + 应用门户。
 * 新增应用 = 在 routes 里加一条记录 + 在 views/ 下加一个视图 + 在门户应用中心加卡片。
 *
 * 采用 history 模式 + 统一尾斜杠（/wedesk/），理由：
 *   1. URL 干净（无 #），与旧官网 /wedesk/ 形态完全一致，旧收录链接零迁移成本；
 *   2. 后端（FastAPI）托管时 spa_fallback 对任意路径返回 index.html，刷新不 404；
 *   3. GitHub Pages 纯静态托管：部署工作流在 build 后 cp index.html 为 404.html，
 *      Pages 对任意深路径返回同一份 SPA 入口，vue-router 按 location.pathname 直接
 *      渲染对应页面，不依赖 sessionStorage 跳转；
 *   4. OAuth2/Logto 的 redirect_uri 禁止带 fragment(#)，history 模式回调落在
 *      /?code=&state=，由 main.ts 在挂载前消费（详见 auth service）。
 *
 * 所有路由 path 以 / 结尾；beforeEach 把无尾斜杠的访问统一重定向，保持 URL 形态一致。
 */
const routes: RouteRecordRaw[] = [
  // ---- 站点首页 = 官网首页（右上角产品九宫格弹窗进入门户能力） ----
  {
    path: '/',
    name: 'home',
    component: () => import('@/website/views/HomePage.vue'),
    meta: { title: '欢迎使用', website: true },
  },
  // 官网旧路径 /home/ 与旧命名路由 'index' 都归一到 /
  {
    path: '/home/',
    name: 'index',
    redirect: '/',
    meta: { website: true },
  },

  // ---- Also Apps 统一应用门户 ----
  {
    path: '/apps-home/',
    name: 'apps-home',
    component: () => import('@/views/AppsHomeView.vue'),
    meta: { title: 'Also Apps' },
  },
  {
    path: '/products/',
    name: 'apps',
    component: () => import('@/views/AppsCenterView.vue'),
    meta: { title: '应用中心' },
  },
  {
    path: '/apps/:code/',
    name: 'app-detail',
    component: () => import('@/views/AppDetailView.vue'),
    meta: { title: '应用详情' },
  },
  {
    path: '/admin/apps/',
    name: 'admin-apps',
    component: () => import('@/views/AdminAppsView.vue'),
    meta: { title: '应用中心管理' },
  },
  // SafeKeep 独立工具：CDN 把 /tools/ 前缀单独回源到旧站，故用根路径 /safekeep/
  {
    path: '/safekeep/',
    name: 'safekeep',
    component: () => import('@/views/SafeKeepView.vue'),
    meta: { title: '锦囊 SafeKeep' },
  },
  // 曾短暂启用的 /tools/safekeep/ 重定向回根路径（CDN 规则修复后才会到达）
  {
    path: '/tools/safekeep/',
    redirect: '/safekeep/',
  },
  // 工具集首页（SafeKeep 等独立工具的卡片入口页）
  {
    path: '/tools-home/',
    name: 'tools-home',
    component: () => import('@/views/HomeView.vue'),
    meta: { title: '工具集' },
  },

  // ---- 官网页面（原 alsoapp.com 主站，meta.website 标记走旧 title 后缀） ----
  {
    path: '/products/',
    name: 'products',
    component: () => import('@/website/views/ProductPage.vue'),
    meta: { title: '产品信息', website: true },
  },
  {
    path: '/products/superset/',
    name: 'superset',
    component: () => import('@/website/views/SupersetPage.vue'),
    meta: { title: 'superset', website: true },
  },
  {
    path: '/wedesk/',
    name: 'wedesk',
    component: () => import('@/website/views/WedeskPage.vue'),
    meta: { title: 'WeDesk 远程桌面', website: true },
  },
  {
    path: '/zaima/',
    name: 'zaima',
    component: () => import('@/website/views/ZaimaPage.vue'),
    meta: { title: '在吗 - 定时签到报平安', website: true },
  },
  {
    path: '/resumes/:user_id/',
    name: 'resumes',
    component: () => import('@/website/views/ResumePage.vue'),
    meta: { title: '简历信息', website: true },
  },
  {
    path: '/privacy/',
    name: 'privacy',
    component: () => import('@/website/views/PrivacyPage.vue'),
    meta: { title: '隐私政策', website: true },
  },
  {
    path: '/terms/',
    name: 'terms',
    component: () => import('@/website/views/TermsPage.vue'),
    meta: { title: '服务条款', website: true },
  },
  {
    path: '/test/',
    name: 'test',
    component: () => import('@/website/views/TestPage.vue'),
    meta: { title: '组件测试', website: true },
  },
  {
    path: '/login/',
    name: 'login',
    component: () => import('@/website/views/LoginPage.vue'),
    meta: { title: '登录', website: true },
  },

  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: '页面不存在' },
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

// 统一 URL 尾斜杠：无尾斜杠的访问（含 404 兜底路径）一律 301 式重定向补齐，
// 与旧官网 /wedesk/ 形态及搜索引擎收录保持一致
router.beforeEach((to) => {
  if (to.path !== '/' && !to.path.endsWith('/')) {
    return { path: to.path + '/', query: to.query, hash: to.hash }
  }
  return true
})

router.afterEach((to) => {
  const title = (to.meta.title as string | undefined) ?? 'Also Apps'
  // 官网页面保持旧后缀「- alsoapp」，门户页面用「· Also Apps」
  document.title = to.meta.website ? `${title} - alsoapp` : `${title} · Also Apps`
})

export default router
