<template>
  <el-container>
    <el-header ref="topNav" style="padding: 0;">
      <MyHeader/>
    </el-header>
    <el-container style="margin-top: 2px;">
      <el-scrollbar :height="scrollHeight">
        <el-aside :style="{'background-color': bg_color}" style="padding-right: 10px" class="text-center p-2">
          <el-menu mode="vertical" :router="true" default-active="/hipmessageservice/service/">
            <el-menu-item index="/hipmessageservice/service/">
              <el-icon size="30">
                <Platform/>
              </el-icon>
              <template #title>交互服务</template>
            </el-menu-item>
            <el-menu-item index="/hipmessageservice/cda/">
              <el-icon size="30">
                <Document/>
              </el-icon>
              <template #title>CDA文档列表</template>
            </el-menu-item>
            <el-menu-item index="/hipmessageservice/dict/">
              <el-icon size="30">
                <Collection/>
              </el-icon>
              <template #title>标准字典参考</template>
            </el-menu-item>
          </el-menu>
          <el-divider></el-divider>
          <el-alert
              title="特别声明"
              type="warning"
              effect="dark"
              description="本文档的目的是为更好的方便大家在技术上的沟通交流,不涉及患者或医院隐私数据,如发现,请联系我们处理!"
              show-icon
              @close="()=>{ is_closed = !is_closed}"
          />
          <el-divider v-show="!is_closed"></el-divider>
          <el-link href="https://pan.baidu.com/s/1DddWS49ydgz79m5yz-ZgOA?pwd=9umj#list/path=%2F" target="_blank"
                   :underline="false">
            <el-button type="danger">相关资料下载</el-button>
          </el-link>
        </el-aside>
      </el-scrollbar>
      <el-main style="padding: 0">
        <el-scrollbar :height="scrollHeight">
          <router-view/>
        </el-scrollbar>
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.el-menu {
  border: 0 !important;
}
</style>
<script setup>

import {computed, ref} from "vue";

import {
  ElHeader, ElContainer, ElMain, ElAside, ElScrollbar, ElIcon, ElMenu, ElMenuItem, ElDivider,
  ElButton, ElLink, ElAlert
} from 'element-plus';   // 按需引入组件
import {Collection, Platform, Document} from '@element-plus/icons-vue' // 按需引入 Icon 图标

// import {messageStore} from "@/store";
import MyHeader from "@/components/MyHeader.vue";


// const {message} = messageStore();
const topNav = ref(null);
const is_closed = ref(false)

// 滚动高度
const scrollHeight = computed(() => {
  if (topNav.value != null) {
    return window.innerHeight - topNav.value.$el.offsetHeight - 10 + 'px';
  }
  return window.innerHeight - 200 + 'px';
})

const bg_color = computed(() => {
  return process.env["VUE_APP_BG_COLOR "]
})

</script>