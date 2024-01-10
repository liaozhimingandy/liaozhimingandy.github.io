<template>
  <p class="text-center p-3">
    <router-link :to="{'name': 'index'}" style="text-decoration: none;" class="text-muted">alsoapp.com&nbsp;</router-link>&copy;<span id="years_now" class="font-weight-bold">&nbsp;{{ new Date().getFullYear() }}&nbsp;</span>
    <span class="font-weight-bold">All&nbsp;Rights&nbsp;Reserved</span>
  </p>
</template>

<script setup>
</script>

<style scoped>

</style>