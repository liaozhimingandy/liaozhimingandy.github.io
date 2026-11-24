<script setup lang="ts">
/**
 * 百度「更多产品」风格的应用列表项：左侧圆角图标，右侧「名称 + 一行简介」。
 * 整项可点：已配置 launch_url 的应用走统一启动流程直达真实页面
 * （含发布状态/登录校验与最近访问记录）；未配置地址的应用才进详情页。
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { PortalApp } from '@/services/portal/api.ts'
import { useAppLaunch } from '@/services/portal/useAppLaunch.ts'

const props = defineProps<{ app: PortalApp }>()
const router = useRouter()
const { launch } = useAppLaunch()

/** 徽标提示文案：字段里没有具体下线日期，文案只说明状态与建议动作。 */
const NEW_TIP = '新品标识：该应用近期上线，功能可能持续更新'
const OFFLINE_TIP = '即将下线：该应用计划停止服务，请谨慎使用并提前备份数据'

const hasBadge = computed(() => props.app.is_new || props.app.is_offline_soon)

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
      <div class="item-head">
        <div class="item-name">{{ app.name }}</div>
        <!-- 状态徽标放在列表项容器内、名称右侧；点徽标不触发启动应用 -->
        <div v-if="hasBadge" class="item-badges" @click.stop>
          <t-tooltip v-if="app.is_new" :content="NEW_TIP" placement="top">
            <span class="item-badge item-badge--new">新品</span>
          </t-tooltip>
          <t-tooltip v-if="app.is_offline_soon" :content="OFFLINE_TIP" placement="top">
            <span class="item-badge item-badge--offline">即将下线</span>
          </t-tooltip>
        </div>
      </div>
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
/* 名称与徽标同一行：名称可压缩省略，徽标始终完整可见 */
.item-head {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.item-badges {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  cursor: help;
}
.item-badge {
  display: inline-block;
  padding: 0 5px;
  border-radius: 4px;
  font-size: 10px;
  line-height: 16px;
  white-space: nowrap;
}
.item-badge--new {
  background: var(--color-success-soft, #e8f8e8);
  color: var(--color-success, #00a870);
}
.item-badge--offline {
  background: var(--color-warning-soft, #fff3e0);
  color: var(--color-warning, #ed7b2f);
}
.item-name {
  flex: 1;
  min-width: 0;
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
