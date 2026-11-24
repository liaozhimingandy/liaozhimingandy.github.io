<script setup lang="ts">
/**
 * 官网首页右上角产品九宫格弹窗（Google 风格）。
 *
 * 数据源：门户公开 API（/v1/portal/apps，published 应用）——后续开发的产品
 * 在门户登记后自动出现在这里，无需改首页代码。
 * 降级：API 失败或为空时展示静态内链兜底（全部走本站路由，不跳外站）。
 * 底部「查看更多产品」进应用中心（/apps）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { GridViewIcon } from 'tdesign-icons-vue-next'
import { listApps, type PortalApp } from '@/services/portal/api.ts'

interface GridItem {
  name: string
  /** 外部产品用 http(s) 地址；本站产品用相对路径（站内跳转） */
  url?: string
  routeName?: string
  /** 本站相对路径且 same_tab 时走 SPA 路由，其余新标签打开 */
  sameTab?: boolean
  color: string
  /** 应用图标链接；为空或加载失败时回退首字母徽标 */
  iconUrl?: string
}

const router = useRouter()
const visible = ref(false)
const apps = ref<PortalApp[]>([])
const failed = ref(false)
/** 加载失败的图标链接——按 URL 记录，换链接会自动重试，不会被旧失败状态粘住 */
const failedIcons = ref<string[]>([])

/** API 不可用时的静态兜底（全是本站路由，保证弹窗永远有内容） */
const FALLBACK: GridItem[] = [
  { name: 'WeDesk', routeName: 'wedesk', color: '#027aff' },
  { name: '在吗', routeName: 'zaima', color: '#0a8756' },
  { name: 'Superset', routeName: 'superset', color: '#7b5cd6' },
]

/** 徽标底色（按名称稳定取色，视觉上区分产品） */
const COLORS = ['#027aff', '#0a8756', '#7b5cd6', '#d03050', '#b26a00', '#0084b4']

onMounted(async () => {
  try {
    const res = await listApps()
    apps.value = res.items
  } catch {
    failed.value = true
  }
})

const items = computed<GridItem[]>(() => {
  if (failed.value || apps.value.length === 0) return FALLBACK
  return apps.value.map((app, i) => ({
    name: app.name,
    url: app.launch_url || undefined,
    sameTab: app.open_mode === 'same_tab',
    color: COLORS[i % COLORS.length],
    iconUrl: app.icon_url?.trim() || undefined,
  }))
})

function badgeText(name: string): string {
  return name.trim().charAt(0).toUpperCase()
}

function showIcon(item: GridItem): boolean {
  return !!item.iconUrl && !failedIcons.value.includes(item.iconUrl)
}

function onIconError(item: GridItem): void {
  if (item.iconUrl && !failedIcons.value.includes(item.iconUrl)) {
    failedIcons.value.push(item.iconUrl)
  }
}

function open(item: GridItem): void {
  visible.value = false
  if (item.routeName) {
    void router.push({ name: item.routeName })
  } else if (item.url) {
    if (item.sameTab && item.url.startsWith('/')) void router.push(item.url)
    else window.open(item.url, '_blank', 'noopener')
  }
}
</script>

<template>
  <t-popup
    v-model="visible"
    trigger="click"
    placement="bottom-right"
    :show-arrow="false"
    overlay-inner-class-name="grid-popup-inner"
  >
    <t-button
      variant="text"
      shape="circle"
      title="Also 产品"
      class="grid-trigger"
    >
      <GridViewIcon size="22px" />
    </t-button>

    <template #content>
      <div class="grid-panel">
        <div class="grid-items">
          <button
            v-for="item in items"
            :key="item.name"
            type="button"
            class="grid-item"
            @click="open(item)"
          >
            <span
              class="grid-badge"
              :style="showIcon(item) ? undefined : { background: item.color }"
            >
              <img
                v-if="showIcon(item)"
                :src="item.iconUrl"
                :alt="item.name"
                class="grid-badge-img"
                @error="onIconError(item)"
              />
              <template v-else>{{ badgeText(item.name) }}</template>
            </span>
            <span class="grid-name">{{ item.name }}</span>
          </button>
        </div>
        <div class="grid-more">
          <router-link
            :to="{ name: 'apps' }"
            class="no-underline text-[13px] text-gray-600 hover:text-brand"
            @click="visible = false"
          >查看更多产品</router-link>
        </div>
      </div>
    </template>
  </t-popup>
</template>

<style scoped>
.grid-trigger {
  color: #5f6368;
}
.grid-panel {
  width: auto;
  min-width: 216px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.16);
  padding: 12px 8px 8px;
}
.grid-items {
  display: grid;
  /* 固定列宽贴合图标，避免 320px 宽面板里 3 列各占 ~93px 造成左右大片留白 */
  grid-template-columns: repeat(3, 64px);
  justify-content: center;
  gap: 4px;
}
.grid-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 10px 2px;
  border: 0;
  background: transparent;
  border-radius: 10px;
  cursor: pointer;
}
.grid-item:hover {
  background: #f0f7fe;
}
.grid-badge {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  user-select: none;
  overflow: hidden;
}
.grid-badge-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.grid-name {
  font-size: 12px;
  color: #1f2329;
  line-height: 1.2;
  text-align: center;
}
.grid-more {
  border-top: 1px solid #e5e8ed;
  margin-top: 8px;
  padding: 8px 0 2px;
  text-align: center;
}
</style>

<!--
  t-popup 内容 teleport 到 body，scoped 的 :deep(.t-popup__content) 会带 data-v-xxx
  属性选择器而匹配不到，故用非 scoped 样式 + overlay-inner-class-name 精准清除
  TDesign 默认的白底/内边距/边框，消除「弹框里再套一张卡片」的灰色间隙。
-->
<style>
.grid-popup-inner.t-popup__content {
  /* TDesign 的方向选择器（.t-popup[data-popper-placement] .t-popup__content）优先级更高，
     这里用 !important 确保「弹窗里再套一张卡片」的白底/内边距/边框被彻底清除。 */
  padding: 0 !important;
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
  border-radius: 0 !important;
}
</style>
