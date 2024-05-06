<template>
  <el-container>
    <el-header ref="topNav" style="padding: 0;">
      <MyHeader/>
    </el-header>
    <el-container style="margin-top: 2px;">
      <el-scrollbar :height="scrollHeight">
        <el-aside :style="{'background-color': bg_color}" style="padding-right: 10px">
          <el-menu default-active="2" mode="vertical">
            <el-menu-item index="2">
              <el-icon size="30">
                <Edit/>
              </el-icon>
              <template #title>菜单一</template>
            </el-menu-item>
            <el-menu-item index="3" disabled>
              <el-icon size="30">
                <DocumentAdd/>
              </el-icon>
              <template #title>菜单二</template>
            </el-menu-item>
            <el-menu-item index="4">
              <el-icon size="30">
                <Setting/>
              </el-icon>
              <template #title>菜单三</template>
            </el-menu-item>
          </el-menu>
          <el-divider></el-divider>
        </el-aside>
      </el-scrollbar>
      <el-main style="padding: 0">
        <el-scrollbar :height="scrollHeight">
          <table class="table table-hover" style="background: white">
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
        </el-scrollbar>
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.el-menu {
  border:0!important;
}
</style>
<script setup>
import {request} from "@/services";
import {onMounted, reactive, computed, ref} from "vue";

import {ElHeader, ElNotification, ElContainer, ElMain, ElAside, ElScrollbar, ElIcon, ElMenu, ElMenuItem, ElDivider} from 'element-plus';   // 按需引入组件
import {Setting, DocumentAdd, Edit} from '@element-plus/icons-vue' // 按需引入 Icon 图标
import {API_ENDPOINTS as api} from "@/services/api";

// import {messageStore} from "@/store";
import MyHeader from "@/components/MyHeader.vue";

// const {message} = messageStore();
const data = reactive({});
const topNav = ref(null);

onMounted(() => {
      request(api.LIST_HIP_SERVICE, 'get')
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

// 滚动高度
const scrollHeight = computed(() => {
  if (topNav.value != null) {
    return window.innerHeight - topNav.value.$el.offsetHeight - 10 + 'px';
  }
  return window.innerHeight - 200 + 'px';
})

const bg_color = computed(()=>{return process.env["VUE_APP_BG_COLOR "]})

</script>