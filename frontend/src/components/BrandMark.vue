<script setup lang="ts">
/**
 * 品牌字标（无图形 Logo）：alsoapp 按 Google 字标风格逐字母分色。
 * 颜色沿用 Google 品牌四色循环：蓝 / 红 / 黄 / 绿；文字代替图标，
 * 仅作视觉标识，不承载任何权限语义。
 */
import { computed } from 'vue'

const props = defineProps<{ size?: string }>()

const LETTERS = ['a', 'l', 's', 'o', 'a', 'p', 'p'] as const
// 用户指定配色：a 蓝 / l 红 / s 黄 / o 蓝 / a 绿 / p 红 / p 黄
const COLORS = ['#4285F4', '#EA4335', '#FBBC05', '#4285F4', '#34A853', '#EA4335', '#FBBC05'] as const

const fontSize = computed(() => props.size ?? '1rem')
</script>

<template>
  <span class="brand-mark" :style="{ fontSize }" aria-label="alsoapp">
    <span
      v-for="(ch, i) in LETTERS"
      :key="i"
      :style="{ color: COLORS[i % COLORS.length] }"
    >{{ ch }}</span>
  </span>
</template>

<style scoped>
.brand-mark {
  display: inline-flex;
  align-items: center;
  gap: 0.01em;
  font-family: 'Google Sans', 'Product Sans', system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif;
  font-weight: 500;
  line-height: 1;
  letter-spacing: 0.01em;
  user-select: none;
}
</style>
