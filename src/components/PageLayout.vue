<template>
  <div class="flex min-h-screen flex-col">
    <!-- 吸顶导航:统一提供返回首页入口与联系方式 -->
    <header class="sticky top-0 z-10 bg-gray-800 px-4 py-3 text-white">
      <div class="mx-auto flex max-w-7xl items-center justify-between gap-3">
        <router-link
            :to="{'name': 'index'}"
            class="flex items-center gap-2 text-base font-semibold text-white no-underline hover:text-brand"
        >
          <img src="/favicon.svg" alt="alsoapp" width="24" height="24"/>
          <span>{{ title }}</span>
        </router-link>
        <MyTooltip/>
      </div>
    </header>

    <!-- 页面主体 -->
    <main class="mx-auto w-full max-w-7xl flex-1 px-4 py-4">
      <slot/>
    </main>

    <!-- 版权信息 -->
    <CopyRight/>
  </div>
</template>

<script setup>
import MyTooltip from "@/components/MyTooltip";
import CopyRight from "@/components/CopyRight";

defineProps({
  // 页面标题,展示在吸顶导航左侧
  title: {
    type: String,
    default: 'alsoapp'
  }
});
</script>
