<script setup lang="ts">
/**
 * 独立应用中心 /apps —— 百度「更多产品」式布局：
 * 分类分组小节 + 四列「图标 + 名称 + 一行简介」列表项（AppListItem）。
 * URL 查询参数（q / category / view）与筛选状态双向同步，便于分享和刷新；
 * 关键词或选中分类时退化为单一平铺小节，其余情况按分类分组展示。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { SearchIcon } from 'tdesign-icons-vue-next'
import PortalHeader from '@/components/PortalHeader.vue'
import AppListItem from '@/components/AppListItem.vue'
import CopyRight from '@/components/CopyRight.vue'
import { usePortalStore } from '@/services/portal/store.ts'
import { searchApps, type PortalApp } from '@/services/portal/api.ts'
import { isAuthenticated } from '@/services/auth/logto.ts'

const route = useRoute()
const router = useRouter()
const { state, loadCatalog, loadUserData } = usePortalStore()

const keyword = ref(String(route.query.q ?? ''))
const category = ref(String(route.query.category ?? 'all'))
const view = ref<'all' | 'favorites' | 'recent'>(
  ['all', 'favorites', 'recent'].includes(String(route.query.view)) ? String(route.query.view) as 'all' | 'favorites' | 'recent' : 'all',
)
const authenticated = ref(false)
const remoteResults = ref<PortalApp[] | null>(null)

// URL ←→ 状态：改动筛选条件时同步到地址栏，支持分享和刷新
watch([keyword, category, view], () => {
  const query: Record<string, string> = {}
  if (keyword.value.trim()) query.q = keyword.value.trim()
  if (category.value !== 'all') query.category = category.value
  if (view.value !== 'all') query.view = view.value
  void router.replace({ name: 'apps', query })
})

const source = computed(() => {
  if (remoteResults.value !== null) return remoteResults.value
  if (view.value === 'favorites') return state.favorites
  if (view.value === 'recent') return state.recent
  return state.apps
})

const filtered = computed(() => {
  let rows = source.value
  if (view.value === 'all' && category.value !== 'all') {
    rows = rows.filter((a) => a.categories.includes(category.value))
  }
  if (keyword.value && remoteResults.value === null) {
    const q = keyword.value.trim().toLowerCase()
    rows = rows.filter((a) => `${a.name} ${a.code} ${a.subtitle} ${a.description}`.toLowerCase().includes(q))
  }
  return rows
})

/** 无任何筛选时按百度式分组展示；一旦筛选（搜索/分类/收藏/最近）则平铺单节。 */
const showGrouped = computed(
  () => view.value === 'all' && !keyword.value.trim() && category.value === 'all',
)

/** 分类 chip 数据源：剔除种子里的 'all' 伪分类（与「全部应用」tab 语义重复） */
const filterCategories = computed(() => state.categories.filter((c) => c.code !== 'all'))

const VIEW_TITLES: Record<string, string> = {
  favorites: '我的收藏',
  recent: '最近使用',
}

const groups = computed<{ title: string; badge?: string; apps: PortalApp[] }[]>(() => {
  if (!showGrouped.value) {
    const title =
      category.value !== 'all'
        ? (state.categories.find((c) => c.code === category.value)?.name ?? '筛选结果')
        : (keyword.value.trim() ? '搜索结果' : (VIEW_TITLES[view.value] ?? '全部应用'))
    return [{ title, apps: filtered.value }]
  }
  const out: { title: string; badge?: string; apps: PortalApp[] }[] = []
  const fresh = state.apps.filter((a) => a.is_new)
  if (fresh.length) out.push({ title: '新上线', badge: '最新', apps: fresh })
  for (const cat of state.categories) {
    const rows = state.apps.filter((a) => a.categories.includes(cat.code))
    if (rows.length) out.push({ title: cat.name, apps: rows })
  }
  const rest = state.apps.filter((a) => !a.categories.length)
  if (rest.length) out.push({ title: '其他', apps: rest })
  return out
})

onMounted(async () => {
  await loadCatalog()
  authenticated.value = await isAuthenticated().catch(() => false)
  if (authenticated.value) await loadUserData(true)
})

// 关键词搜索走后端接口（覆盖 code 等前端缓存可能不含的字段）
let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(keyword, (value) => {
  if (searchTimer) clearTimeout(searchTimer)
  if (!value.trim()) { remoteResults.value = null; return }
  searchTimer = setTimeout(async () => {
    try {
      const res = await searchApps(value.trim(), category.value === 'all' ? '' : category.value)
      remoteResults.value = res.items
    } catch {
      remoteResults.value = null  // 搜索失败回退本地过滤
    }
  }, 250)
})
watch(category, () => {
  if (remoteResults.value !== null && keyword.value.trim()) {
    void searchApps(keyword.value.trim(), category.value === 'all' ? '' : category.value)
      .then((res) => { remoteResults.value = res.items })
      .catch(() => { remoteResults.value = null })
  }
})

function clearFilters(): void {
  keyword.value = ''
  category.value = 'all'
  view.value = 'all'
  remoteResults.value = null
}
</script>

<template>
  <PortalHeader />

  <main class="mx-auto max-w-6xl px-4 pb-16">
    <div class="flex items-center justify-between flex-wrap gap-3 mb-6">
      <div>
        <h1 class="text-[26px] font-bold">应用中心</h1>
        <p class="text-[13.5px] text-ink-3 mt-1.5">发现 Alsoapp 生态的全部应用与工具</p>
      </div>
      <t-input v-model="keyword" class="w-[300px]" placeholder="搜索名称、编码或功能" clearable>
        <template #prefix-icon><SearchIcon /></template>
      </t-input>
    </div>

    <t-tabs v-model="view" class="view-tabs">
      <t-tab-panel value="all" label="全部应用" />
      <t-tab-panel value="favorites" label="我的收藏" />
      <t-tab-panel value="recent" label="最近使用" />
    </t-tabs>

    <div class="category-bar">
      <button
        v-for="cat in filterCategories"
        :key="cat.code"
        type="button"
        class="category-chip"
        :class="{ 'category-chip--active': category === cat.code }"
        @click="category = category === cat.code ? 'all' : cat.code"
      >
        {{ cat.name }}
      </button>
    </div>

    <t-loading :loading="state.loading && !state.loaded" size="small" class="min-h-[200px]">
      <!-- 百度式分组：新上线 + 各分类小节 -->
      <section v-for="g in groups" :key="g.title" class="group-section">
        <div class="flex items-center gap-2 mb-4">
          <h2 class="text-[16px] font-semibold text-ink">{{ g.title }}</h2>
          <span v-if="g.badge" class="new-badge">{{ g.badge }}</span>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-5">
          <AppListItem v-for="app in g.apps" :key="app.id" :app="app" />
        </div>
      </section>

      <div v-if="!filtered.length && !state.loading" class="text-center py-16 text-ink-3">
        没有找到匹配的应用。<t-link theme="primary" @click="clearFilters">清除筛选</t-link>
      </div>
    </t-loading>
  </main>

  <CopyRight />
</template>

<style scoped>
/* 视图 tab 与分类 chip 行之间留足呼吸感，避免两行筛选控件挤在一起 */
.view-tabs {
  margin-bottom: 4px;
}
.view-tabs :deep(.t-tabs__content) {
  display: none;
}
.category-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 0 4px;
  border-top: 1px solid var(--color-line, #e7e9ec);
}
.category-chip {
  padding: 7px 16px;
  border-radius: 999px;
  border: 1px solid var(--color-line);
  background: var(--color-surface);
  color: var(--color-ink-2);
  font-size: 13px;
  line-height: 1.4;
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease, background 0.15s ease;
}
.category-chip:hover {
  color: var(--color-brand);
  border-color: var(--color-brand);
}
.category-chip--active {
  background: var(--color-brand-soft);
  border-color: var(--color-brand);
  color: var(--color-brand);
}
.group-section {
  margin-top: 36px;
}
.group-section:first-of-type {
  margin-top: 30px;
}
.new-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 4px;
  background: #ff8800;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  line-height: 18px;
}
</style>
