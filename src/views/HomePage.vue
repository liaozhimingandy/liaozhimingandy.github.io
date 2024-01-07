<template>
  <nav class="navbar sticky-top bg-light border-bottom border-body">
    <div class="container">
      <a class="navbar-brand" href="/">
        <img src="https://www.alsoapp.com/favicon.svg" alt="alsoapp" width="30" height="24">
      </a>
      <span class="navbar-text">
                此网站维护中... 你可以提供宝贵的意见或建议;<a href="mailto:liaozhimingandy@qq.com" class="text-muted">点击此处打开邮箱客户端用于发送邮件</a>
            </span>
    </div>
  </nav>
  <br>
  <div class="container">
    <div class="alert alert-warning alert-dismissible fade show" role="alert">
      <strong>
        <router-link :to="{'name': 'products'}" class="text-muted">更多</router-link>
      </strong>
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    </div>

    <div class="card">
      <h6 class="card-header">
        请联系我们,我们很乐意为你服务!
      </h6>
      <div class="card-body">
        <img src="/static/contact-us-wechat.jpg" height="400px"/>
      </div>
    </div>
  </div>

</template>

<script setup>

</script>

<style scoped>

</style>