<template>
  <div class="text-bg-light p-3 bg-transparent">
    <p class="text-center m-0">
      <router-link :to="{'name': 'index'}" style="text-decoration: none;" class="text-muted">alsoapp.com&nbsp;
      </router-link>&copy;<span id="years_now" class="font-weight-bold">&nbsp;{{
        new Date().getFullYear()
      }}&nbsp;</span>
      <span class="font-weight-bold">All&nbsp;Rights&nbsp;Reserved</span>&nbsp;&nbsp;
      <span class="text-muted">version:{{ APP_VERBOSE }}</span>&nbsp;&nbsp;
      <router-link :to="{'name': 'privacy'}" style="text-decoration: none;" class="btn btn-light">隐私政策</router-link>
      &nbsp;|&nbsp;<a class="btn btn-light" href="https://www.apache.org/licenses/LICENSE-2.0" target="_blank">licenses</a>
    </p>
  </div>
</template>

<script setup>
import {computed} from "vue";

const APP_VERBOSE = computed(() => {
  return process.env.VUE_APP_VERSION+" | "+process.env.COMMIT_HASH.substring(0, 7);
});
</script>

<style scoped>
</style>