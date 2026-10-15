<script setup>
import {ref} from "vue";
import {MessagePlugin} from 'tdesign-vue-next';

const loginModel = ref({
  "username": '',
  "password": ''
})

function login() {
  if (!loginModel.value.username || !loginModel.value.password) {
    MessagePlugin.warning('请输入用户名和密码');
    return;
  }
  console.debug("login")
  MessagePlugin.success('登录成功');
}
</script>


<template>
  <t-layout>
    <t-content>
      <t-card class="box-card">
        <div class="clearfix">
          <span>登录</span>
        </div>
        <t-form label-width="70px">
          <t-form-item label="用户名" name="username">
            <t-input v-model="loginModel.username" clearable placeholder="请输入用户名"></t-input>
          </t-form-item>
          <t-form-item label="密码" name="password">
            <t-input type="password" v-model="loginModel.password" clearable placeholder="请输入密码"></t-input>
          </t-form-item>
          <t-button theme="primary" @click="login" class="full-width-button">登录</t-button>
        </t-form>
      </t-card>
    </t-content>
  </t-layout>
</template>

<style scoped>
.box-card {
  width: 300px;
  margin: 100px auto;
}

.full-width-button {
  width: 80%;
  display: block;
  margin: auto
}
</style>
