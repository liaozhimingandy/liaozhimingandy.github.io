<template>
  <el-container>
    <h1>测试</h1>
    <h4>{{ message }}</h4>
    <el-button type="primary" :icon="Edit">编辑
    </el-button>
    <table class="table table-hover">
      <tbody>
      <tr v-for="(item, index) in data.data" :key="index">
        <th scope="row">{{ item[0] }}</th>
        <td>{{ item[1] }}</td>
        <td>{{ item[2] }}</td>
        <td>{{ item[3] }}</td>
        <td>{{ item[4] }}</td>
      </tr>
      </tbody>
    </table>
  </el-container>
</template>

<style scoped>

</style>
<script setup>
import service from "@/services";
import {onMounted, reactive} from "vue";

import {ElNotification} from 'element-plus';
import {ElButton} from 'element-plus';   // 按需引入组件
import {Edit} from '@element-plus/icons-vue' // 按需引入 Icon 图标
import {API_ENDPOINTS as api} from "@/services/api";

import {messageStore} from "@/store";
const {message} = messageStore();

const data = reactive({});

onMounted(() => {
      service.get(api.LIST_HIP_SERVICE)
          .then(response => {
            data.data = response.data;
            ElNotification({
              title: '温馨提示',
              message: '已成功加载' + data.data.length + '条数据',
              type: 'success',
              position: 'bottom-right'
            });
          })
          .catch(error => {
            console.error(error);
          });
    }
);
</script>