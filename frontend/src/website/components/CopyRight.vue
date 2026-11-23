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

const APP_VERBOSE = computed(() => {
  return process.env.VUE_APP_VERSION + " | " + process.env.COMMIT_HASH.substring(0, 7);
});
</script>
