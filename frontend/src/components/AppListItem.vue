<script setup lang="ts">
/**
 * 百度「更多产品」风格的应用列表项：左侧圆角图标，右侧「名称 + 一行简介」。
 * 整项可点：已配置 launch_url 的应用走统一启动流程直达真实页面
 * （含发布状态/登录校验与最近访问记录）；未配置地址的应用才进详情页。
 */
import { useRouter } from 'vue-router'
import type { PortalApp } from '@/services/portal/api.ts'
import { useAppLaunch } from '@/services/portal/useAppLaunch.ts'

const props = defineProps<{ app: PortalApp }>()
const router = useRouter()
const { launch } = useAppLaunch()

function open(): void {
  if (props.app.launch_url) void launch(props.app)
  else void router.push({ name: 'app-detail', params: { code: props.app.code } })
}
</script>

<template>
  <button type="button" class="app-list-item" @click="open">
    <div class="item-icon shrink-0">
      <img v-if="app.icon_url" :src="app.icon_url" :alt="app.name" class="w-full h-full object-cover" />
      <span v-else>{{ app.name.charAt(0).toUpperCase() }}</span>
    </div>
    <div class="item-text">
      <div class="item-name">{{ app.name }}</div>
      <div class="item-desc" :title="app.subtitle || app.description">
        {{ app.subtitle || app.description || '暂无简介' }}
      </div>
    </div>
  </button>
</template>

<style scoped>
.app-list-item {
  /* width:100% 兜底：button 在部分全局样式下会收缩为内容宽，导致文字逐字换行 */
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-width: 0;
  padding: 8px 10px;
  margin: -8px -10px; /* 视觉上对齐网格，hover 高亮区外扩一圈 */
  border: 0;
  background: transparent;
  border-radius: 10px;
  cursor: pointer;
  text-align: left;
}
.app-list-item:hover {
  background: var(--color-brand-softer, #f5f8ff);
}
.app-list-item:hover .item-name {
  text-decoration: underline;
}
.item-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-brand-soft, #eef3ff);
  color: var(--color-brand, #0052d9);
  font-weight: 700;
  font-size: 16px;
  overflow: hidden;
}
.item-text {
  flex: 1;
  min-width: 0;
}
.item-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-brand, #0052d9);
  line-height: 1.45;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.item-desc {
  font-size: 12.5px;
  color: var(--color-ink-3, #8a94a6);
  line-height: 1.5;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
