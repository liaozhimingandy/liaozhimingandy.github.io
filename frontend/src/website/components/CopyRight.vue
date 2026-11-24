<template>
  <div class="py-3 text-center text-sm text-gray-500">
    <p class="m-0">
      <router-link :to="{'name': 'index'}" class="no-underline hover:text-brand">alsoapp.com&nbsp;</router-link>
      &copy;
      <span class="font-bold">&nbsp;{{ new Date().getFullYear() }}&nbsp;</span>
      <span class="font-bold">All&nbsp;Rights&nbsp;Reserved</span>&nbsp;&nbsp;
      <span>version:{{ APP_VERBOSE }}</span>&nbsp;&nbsp;
      <router-link :to="{'name': 'privacy'}" class="no-underline px-2 text-gray-500 hover:text-brand">隐私政策</router-link>
      &nbsp;|&nbsp;
      <t-link theme="default" href="https://www.apache.org/licenses/LICENSE-2.0" target="_blank" hover="color">
        licenses
      </t-link>
    </p>
  </div>
</template>

<script setup>
import {computed} from "vue";

// 构建版本信息:Vite 下经 define 注入 __APP_VERSION__ / __COMMIT_HASH__(见 vite.config.ts),
// 不可用(如单测环境)时降级为 unknown
const APP_VERBOSE = computed(() => {
  const version = typeof __APP_VERSION__ === "string" ? __APP_VERSION__ : "unknown";
  const hash = typeof __COMMIT_HASH__ === "string" ? __COMMIT_HASH__.substring(0, 7) : "";
  return hash ? `${version} | ${hash}` : version;
});
</script>
