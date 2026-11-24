<script setup lang="ts">
/**
 * 通用骨架屏占位：数据加载中时用与真实布局相近的灰块 + 微光动画占位，
 * 避免「加载中转圈」造成的空白跳动，体验更平滑。
 *
 * variant:
 *  - grid   : 卡片网格（应用中心 / 首页 / 首页展示）
 *  - table  : 表格行（后台应用列表 / 分类管理）
 *  - detail : 详情页（图标 + 标题 + 段落）
 *  - rows / cols 控制占位数量；respects prefers-reduced-motion 关闭动画。
 */
withDefaults(defineProps<{
  variant?: 'grid' | 'table' | 'detail'
  rows?: number
  cols?: number
}>(), {
  variant: 'grid',
  rows: 8,
  cols: 4,
})
</script>

<template>
  <div
    class="skeleton"
    :class="`skeleton--${variant}`"
    role="status"
    aria-label="内容加载中"
    aria-busy="true"
  >
    <template v-if="variant === 'grid'">
      <div v-for="i in rows" :key="i" class="sk-card">
        <div class="sk-block sk-icon"></div>
        <div class="sk-block sk-line sk-line--title"></div>
        <div class="sk-block sk-line sk-line--sub"></div>
      </div>
    </template>

    <template v-else-if="variant === 'table'">
      <div v-for="i in rows" :key="i" class="sk-row">
        <div v-for="j in cols" :key="j" class="sk-block sk-cell"></div>
      </div>
    </template>

    <template v-else>
      <div class="sk-detail-head">
        <div class="sk-block sk-detail-icon"></div>
        <div class="sk-detail-lines">
          <div class="sk-block sk-line sk-line--title"></div>
          <div class="sk-block sk-line sk-line--sub"></div>
          <div class="sk-block sk-line sk-line--sub short"></div>
          <div class="sk-block sk-pill-row"></div>
        </div>
      </div>
      <div class="sk-block sk-detail-panel"></div>
      <div class="sk-block sk-detail-panel short"></div>
    </template>
  </div>
</template>

<style scoped>
.skeleton {
  width: 100%;
}
.sk-block {
  background: linear-gradient(
    100deg,
    var(--color-line) 20%,
    var(--color-canvas) 40%,
    var(--color-line) 60%
  );
  background-size: 200% 100%;
  animation: sk-shimmer 1.4s ease-in-out infinite;
  border-radius: 6px;
}
@keyframes sk-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
@media (prefers-reduced-motion: reduce) {
  .sk-block { animation: none; background: var(--color-line); }
}

/* ---- 卡片网格 ---- */
.skeleton--grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 20px 24px;
}
@media (max-width: 1024px) {
  .skeleton--grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 640px) {
  .skeleton--grid { grid-template-columns: 1fr; }
}
.sk-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
  border: 1px solid var(--color-line);
  border-radius: 12px;
  background: var(--color-surface);
}
.sk-icon { width: 44px; height: 44px; border-radius: 11px; }
.sk-line { height: 13px; border-radius: 5px; }
.sk-line--title { width: 60%; height: 15px; }
.sk-line--sub { width: 90%; }

/* ---- 表格行 ---- */
.skeleton--table {
  border: 1px solid var(--color-line);
  border-radius: 8px;
  overflow: hidden;
}
.sk-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-line);
  background: var(--color-surface);
}
.sk-row:nth-child(even) { background: var(--color-canvas); }
.sk-row:last-child { border-bottom: 0; }
.sk-cell { height: 14px; flex: 1 1 0; min-width: 24px; }
.sk-cell:first-child { flex: 1.6 1 0; }

/* ---- 详情 ---- */
.skeleton--detail { display: flex; flex-direction: column; gap: 20px; }
.sk-detail-head {
  display: flex;
  gap: 20px;
  padding: 24px;
  border: 1px solid var(--color-line);
  border-radius: 16px;
  background: var(--color-surface);
}
.sk-detail-icon { width: 72px; height: 72px; border-radius: 16px; flex: 0 0 auto; }
.sk-detail-lines { flex: 1; display: flex; flex-direction: column; gap: 12px; justify-content: center; }
.sk-detail-lines .short { width: 45%; }
.sk-pill-row { width: 40%; height: 24px; border-radius: 999px; }
.sk-detail-panel {
  height: 140px;
  border: 1px solid var(--color-line);
  border-radius: 12px;
  background: var(--color-surface);
  /* 面板用条纹理，避免整块高亮过于刺眼 */
  background-image: linear-gradient(100deg, transparent 20%, var(--color-canvas) 40%, transparent 60%);
  background-size: 200% 100%;
  animation: sk-shimmer 1.4s ease-in-out infinite;
}
.sk-detail-panel.short { height: 90px; }
@media (prefers-reduced-motion: reduce) {
  .sk-detail-panel { animation: none; background-image: none; }
}
</style>
