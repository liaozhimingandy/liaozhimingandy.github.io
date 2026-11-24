<script setup lang="ts">
import BeianInfo from '@/components/BeianInfo.vue'
/** Also Apps 统一页脚：关于 / 联系 / 隐私 / 服务条款 / 版权。全部走本站路由，不跳外站。 */
const year = new Date().getFullYear()
</script>

<template>
  <footer class="footer">
    <div class="mx-auto max-w-6xl px-4 flex flex-col items-center gap-3">
      <div class="w-full flex flex-col sm:flex-row items-center justify-between gap-3">
        <div class="flex flex-wrap items-center justify-center gap-4 text-[12px]">
          <router-link :to="{ name: 'home' }" class="text-ink-3 hover:text-brand no-underline">关于 Alsoapp</router-link>
          <a href="mailto:contact@alsoapp.com" class="text-ink-3 hover:text-brand no-underline">联系我们</a>
          <router-link :to="{ name: 'privacy' }" class="text-ink-3 hover:text-brand no-underline">隐私政策</router-link>
          <router-link :to="{ name: 'terms' }" class="text-ink-3 hover:text-brand no-underline">服务条款</router-link>
          <router-link :to="{ name: 'apps' }" class="text-ink-3 hover:text-brand no-underline">应用中心</router-link>
        </div>
        <div class="text-[12px] text-ink-3">© {{ year }} AlsoApps · All rights reserved.</div>
      </div>
      <div class="text-[12px] text-ink-3"><BeianInfo /></div>
    </div>
  </footer>
</template>

<style scoped>
.footer {
  margin-top: auto;
  padding: 24px 0;
  border-top: 1px solid var(--color-line);
  background: var(--color-surface);
}
</style>
