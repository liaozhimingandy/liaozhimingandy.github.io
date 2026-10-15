<template>
  <t-layout>
    <t-header ref="topNav" class="!p-0">
      <MyHeader/>
    </t-header>
    <t-layout class="!mt-[2px]">
      <div class="overflow-y-auto" :style="{height: scrollHeight}">
        <t-aside :style="{'background-color': bg_color}" class="p-2 pr-[10px] text-center">
          <t-menu class="!border-0" :value="activeMenu" @change="onMenuChange">
            <t-menu-item value="/hipmessageservice/service/">
              <ServiceIcon size="28px"/>
              <template #title>交互服务</template>
            </t-menu-item>
            <t-menu-item value="/hipmessageservice/cda/">
              <FileIcon size="28px"/>
              <template #title>CDA文档列表</template>
            </t-menu-item>
            <t-menu-item value="/hipmessageservice/dict/">
              <BookIcon size="28px"/>
              <template #title>标准字典参考</template>
            </t-menu-item>
          </t-menu>

          <t-divider/>

          <t-alert
              theme="warning"
              title="特别声明"
              message="本文档的目的是为更好的方便大家在技术上的沟通交流,不涉及患者或医院隐私数据,如发现,请联系我们处理!"
              :close="true"
              @close="()=>{ is_closed = !is_closed}"
          />

          <t-divider v-show="!is_closed"></t-divider>

          <t-link
              href="https://pan.baidu.com/s/1DddWS49ydgz79m5yz-ZgOA?pwd=9umj#list/path=%2F"
              target="_blank"
              :underline="false"
          >
            <t-button theme="danger">相关资料下载</t-button>
          </t-link>
        </t-aside>
      </div>

      <t-content class="!p-0">
        <div class="overflow-y-auto" :style="{height: scrollHeight}">
          <router-view/>
        </div>
      </t-content>
    </t-layout>
  </t-layout>
</template>

<script setup>
import {computed, ref} from "vue";
import {useRoute, useRouter} from "vue-router";
import {ServiceIcon, FileIcon, BookIcon} from 'tdesign-icons-vue-next'

import MyHeader from "@/components/MyHeader.vue";

const route = useRoute();
const router = useRouter();

const topNav = ref(null);
const is_closed = ref(false)
// 当前激活的侧边菜单,与路由保持同步
const activeMenu = ref(route.path.includes('/cda/') ? '/hipmessageservice/cda/'
    : route.path.includes('/dict/') ? '/hipmessageservice/dict/'
        : '/hipmessageservice/service/')

// 菜单切换时跳转路由
function onMenuChange(value) {
  activeMenu.value = value;
  router.push(value);
}

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
