<script setup>
import {ref} from "vue";

import {
  ElContainer,
  ElMain,
  ElCard,
  ElForm,
  ElFormItem,
  ElInput,
  ElButton
} from 'element-plus';   // 按需引入组件

const loginModel = ref({
"username": '',
"password": ''
})


function login(){
  console.debug("login")
}
</script>


<template>
  <el-container>
    <el-main>
      <el-card class="box-card">
        <div class="clearfix">
          <span>登录</span>
        </div>
        <el-form>
          <el-form-item label="用户名" prop="username">
            <el-input v-model="loginModel.username"></el-input>
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input type="password" v-model="loginModel.password"></el-input>
          </el-form-item>
          <el-button type="primary" @click="login" class="full-width-button">登录</el-button>
        </el-form>
      </el-card>
    </el-main>
  </el-container>
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
  /* 可以添加其他样式 */
}
</style>