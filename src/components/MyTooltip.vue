<template>
  <a href="mailto:liaozhimingandy@qq.com" class="text-light" style="text-decoration: none;"
     data-bs-toggle="tooltip" data-bs-placement="bottom"
     data-bs-custom-class="custom-tooltip"
     data-bs-title="通过邮件联系我们;邮箱地址: liaozhimingandy@qq.com">联系我们</a>
</template>

<script setup>
import {onMounted} from "vue";

import {Tooltip} from 'bootstrap'

onMounted(() => {
  new Tooltip(document.body, {
        selector: "[data-bs-toggle='tooltip']", // 加入这一句，生效所有的 data-bs-toogle 绑定
      })})

</script>

<style scoped>

</style>