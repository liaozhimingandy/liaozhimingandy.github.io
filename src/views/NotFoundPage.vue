<template>
  <div
      class="grid min-h-screen items-center bg-cover bg-center p-10"
      :style="{backgroundImage: `url(${notFoundBg})`}"
  >
    <div class="mx-auto w-full max-w-xl">
      <div class="mb-6 text-5xl font-semibold text-white">404
        <span class="ml-2 inline-block text-red-500">Error</span>
      </div>

      <div class="bg-gray-50 p-10 text-center">
        <div class="mb-10 flex justify-center gap-1 text-[100px] font-extrabold leading-none">
          <span class="text-cyan-400">4</span>
          <span class="text-emerald-400">0</span>
          <span class="text-pink-400">4</span>
        </div>
        <h1 class="mb-2 text-4xl font-semibold">Page Not Found</h1>
        <p class="mb-4 text-base text-gray-500">对不起，页面丢失了，请返回首页或者联系我们哦</p>
        <router-link
            :to="{'name': 'index'}"
            class="inline-block bg-gray-900 px-4 py-2 text-sm uppercase tracking-widest text-white hover:bg-red-500"
        >返回首页
        </router-link>
      </div>

      <div class="mt-8">
        <CopyRight/>
      </div>
    </div>
  </div>
</template>

<script setup>
import CopyRight from "@/components/CopyRight";
import notFoundBg from "@/assets/404.jpg";
</script>
