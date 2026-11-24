<script setup lang="ts">
/**
 * 百度「更多产品」风格的应用列表项：左侧圆角图标，右侧「名称 + 一行简介」。
 * 整项可点，进入应用详情页；不做收藏等次要操作，保持列表纯净。
 */
import { useRouter } from 'vue-router'
import type { PortalApp } from '@/services/portal/api.ts'

const props = defineProps<{ app: PortalApp }>()
const router = useRouter()

function open(): void {
  void router.push({ name: 'app-detail', params: { code: props.app.code } })
}
</script>

<template>
  <button type="button" class="app-list-item" @click="open">
    <div class="item-icon shrink-0">
      <img v-if="app.icon_url" :src="app.icon_url" :alt="app.name" class="w-full h-full object-cover" />
      <span v-else>{{ app.name.charAt(0).toUpperCase() }}</span>
    </div>
    <div class="min-w-0 flex-1 text-left">
      <div class="item-name">{{ app.name }}</div>
      <div class="item-desc" :title="app.subtitle || app.description">
        {{ app.subtitle || app.description || '暂无简介' }}
      </div>
    </div>
  </button>
</template>

<style scoped>
.app-list-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 6px 8px;
  margin: -6px -8px; /* 视觉上对齐网格，hover 高亮区外扩一圈 */
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
  width: 36px;
  height: 36px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-brand-soft, #eef3ff);
  color: var(--color-brand, #0052d9);
  font-weight: 700;
  font-size: 15px;
  overflow: hidden;
}
.item-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-brand, #0052d9);
  line-height: 36px; /* 与图标垂直居中：无简介时名称行撑满图标高度 */
}
.item-desc {
  font-size: 12.5px;
  color: var(--color-ink-3, #8a94a6);
  line-height: 1.5;
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* 有简介时名称行恢复正常行高，整体仍与图标对齐 */
.item-name:has(+ .item-desc) {
  line-height: 1.5;
  margin-top: 2px;
}
</style>
