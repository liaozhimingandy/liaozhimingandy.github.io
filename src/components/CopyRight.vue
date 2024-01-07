<template>
  <p class="text-center p-3">
    <router-link :to="{'name': 'index'}" style="text-decoration: none;" class="text-muted">alsoapp.com&nbsp;</router-link>&copy;<span id="years_now" class="font-weight-bold">&nbsp;{{ years_now }}&nbsp;</span>
    <span class="font-weight-bold">All&nbsp;Rights&nbsp;Reserved</span>
  </p>
</template>

<script setup>
  import {ref} from "vue";

  const years_now = ref(new Date().getFullYear());

</script>

<style scoped>

</style>