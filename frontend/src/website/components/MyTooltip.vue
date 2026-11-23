<template>
  <t-tooltip content="通过邮件联系我们;邮箱地址: contact@alsoapp.com" placement="bottom">
    <!-- 深色导航背景下需强制白色,否则 TDesign 默认链接色与深蓝背景对比度不足 -->
    <t-link
        class="!text-white hover:!opacity-80"
        theme="default"
        href="mailto:contact@alsoapp.com"
    >
      <template #prefix-icon>
        <MailIcon/>
      </template>
      联系我们
    </t-link>
  </t-tooltip>
</template>

<script setup>
import {MailIcon} from 'tdesign-icons-vue-next';
</script>
