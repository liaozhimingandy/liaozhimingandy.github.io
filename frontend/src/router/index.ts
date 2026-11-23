import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'

/**
 * Also Apps 统一站点路由表 = 应用门户 + 官网页面。
 * 新增应用 = 在 routes 里加一条记录 + 在 views/ 下加一个视图 + 在门户首页加卡片。
 *
 * 采用 hash 模式（/#/safekeep），原因有三：
 *   1. GitHub Pages 是纯静态托管，history 模式直接刷新 /safekeep 会 404，hash 不发给服务器；
 *   2. OAuth2/Logto 的 redirect_uri 禁止带 fragment(#)，hash 路由让回调落在站点根上，
 *      由 main.ts 在挂载前消费 code/state，再 replace 到 #/safekeep（详见 auth service）；
 *   3. 后端（FastAPI）托管 dist 时同一份产物在 /ap/ 前缀下也能直接运行，无需 history 回退配置。
 *
 * 旧官网 history 链接（/wedesk/ 等）的兼容：index.html 中的内联脚本会把「非根路径且无 hash」
 * 的访问重定向到 /#<原路径>，旧收录链接仍可到达对应页面。
 */
const routes: RouteRecordRaw[] = [
  // ---- Also Apps 统一应用门户（站点首页即门户） ----
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/AppsHomeView.vue'),
    meta: { title: 'Also Apps' },
  },
  {
    path: '/apps',
    name: 'apps',
    component: () => import('@/views/AppsCenterView.vue'),
    meta: { title: '应用中心' },
  },
  {
    path: '/apps/:code',
    name: 'app-detail',
    component: () => import('@/views/AppDetailView.vue'),
    meta: { title: '应用详情' },
  },
  {
    path: '/admin/apps',
    name: 'admin-apps',
    component: () => import('@/views/AdminAppsView.vue'),
    meta: { title: '应用中心管理' },
  },
  {
    path: '/safekeep',
    name: 'safekeep',
    component: () => import('@/views/SafeKeepView.vue'),
    meta: { title: '锦囊 SafeKeep' },
  },
  // 工具集首页（SafeKeep 等独立工具的卡片入口页）
  {
    path: '/tools-home',
    name: 'tools-home',
    component: () => import('@/views/HomeView.vue'),
    meta: { title: '工具集' },
  },

  // ---- 官网页面（原 alsoapp.com 主站，meta.website 标记走旧 title 后缀） ----
  {
    path: '/home',
    name: 'index',
    component: () => import('@/website/views/HomePage.vue'),
    meta: { title: '欢迎使用', website: true },
  },
  {
    path: '/products',
    name: 'products',
    component: () => import('@/website/views/ProductPage.vue'),
    meta: { title: '产品信息', website: true },
  },
  {
    path: '/products/superset',
    name: 'superset',
    component: () => import('@/website/views/SupersetPage.vue'),
    meta: { title: 'superset', website: true },
  },
  {
    path: '/wedesk',
    name: 'wedesk',
    component: () => import('@/website/views/WedeskPage.vue'),
    meta: { title: 'WeDesk 远程桌面', website: true },
  },
  {
    path: '/zaima',
    name: 'zaima',
    component: () => import('@/website/views/ZaimaPage.vue'),
    meta: { title: '在吗 - 定时签到报平安', website: true },
  },
  {
    path: '/resumes/:user_id',
    name: 'resumes',
    component: () => import('@/website/views/ResumePage.vue'),
    meta: { title: '简历信息', website: true },
  },
  {
    path: '/privacy',
    name: 'privacy',
    component: () => import('@/website/views/PrivacyPage.vue'),
    meta: { title: '隐私政策', website: true },
  },
  {
    path: '/test',
    name: 'test',
    component: () => import('@/website/views/TestPage.vue'),
    meta: { title: '组件测试', website: true },
  },
  {
    path: '/login',
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
  history: createWebHashHistory(),
  routes,
})

router.afterEach((to) => {
  const title = (to.meta.title as string | undefined) ?? 'Also Apps'
  // 官网页面保持旧后缀「- alsoapp」，门户页面用「· Also Apps」
  document.title = to.meta.website ? `${title} - alsoapp` : `${title} · Also Apps`
})

export default router
