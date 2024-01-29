<template>
  <div class="text-bg-light p-3">
    <p class="text-center m-0">
      <router-link :to="{'name': 'index'}" style="text-decoration: none;" class="text-muted">alsoapp.com&nbsp;
      </router-link>&copy;<span id="years_now" class="font-weight-bold">&nbsp;{{
        new Date().getFullYear()
      }}&nbsp;</span>
      <span class="font-weight-bold">All&nbsp;Rights&nbsp;Reserved</span>&nbsp;&nbsp;<span class="text-muted">@{{ APP_VERBOSE }}</span></p>
  </div>
</template>

<script setup>
import {computed} from "vue";

const APP_VERBOSE = computed(() => {
  return process.env.VUE_APP_ENV+" • "+process.env.BRANCH+" • "+process.env.COMMIT_HASH.substring(0, 7);
});

</script>

<style scoped>

</style>