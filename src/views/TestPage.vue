<template>
  <t-layout>
    <t-header ref="MaintopNav" class="!p-0">
      <MainTopNav/>
    </t-header>
    <t-layout class="!mt-[2px]">
      <!--      左边侧边栏 -->
      <div class="overflow-y-auto" :style="{height: scrollHeight}">
        <t-aside :style="{'background-color': bg_color}">
          <t-menu value="1">
            <t-menu-item value="1">
              <svg class="icon" viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg" width="28" height="28">
                <path
                    d="M555.541333 117.994667l312.874667 224.565333A117.333333 117.333333 0 0 1 917.333333 437.866667V800c0 64.8-52.533333 117.333333-117.333333 117.333333H640V746.666667c0-70.688-57.312-128-128-128s-128 57.312-128 128v170.666666H224c-64.8 0-117.333333-52.533333-117.333333-117.333333V437.877333a117.333333 117.333333 0 0 1 48.917333-95.317333l312.874667-224.565333a74.666667 74.666667 0 0 1 87.082666 0z"
                    fill="#0089FF"></path>
              </svg>
              <template #title>首页</template>
            </t-menu-item>
          </t-menu>

          <div class="flex justify-center p-3">
            <t-button theme="primary" size="large" @click="openPost">发帖</t-button>
          </div>

          <t-divider/>

          <p class="text-center text-sm text-gray-500">
            alsoapp &copy; {{ new Date().getFullYear() }}
          </p>
        </t-aside>
      </div>

      <!--     内容    -->
      <t-content class="!p-0">
        <div class="overflow-y-auto" :style="{height: scrollHeight}">
          <div class="mx-auto w-2/3 space-y-4 py-4">
            <t-card shadow class="[&_.t-card__body]:!p-0">
              <template #header>Yummy hamburger</template>
              <img
                  src="https://shadow.elemecdn.com/app/element/hamburger.9cf7b091-55e9-11e9-a976-7f4d0b07eef6.png"
                  class="h-[300px] w-full object-cover"
              />
              <template #footer>Footer content</template>
            </t-card>

            <t-card shadow class="[&_.t-card__body]:!p-0">
              <template #header>
                <div class="flex items-center gap-3">
                  <t-avatar
                      image="https://cube.elemecdn.com/0/88/03b0d39583f48206768a7534e55bcpng.png"
                      size="large"
                  />
                  <div class="flex-1">
                    <div>test</div>
                    <div>2</div>
                  </div>
                  <div class="flex items-center gap-2">
                    <EllipsisIcon/>
                    <CloseIcon/>
                  </div>
                </div>
              </template>
              <img
                  src="https://shadow.elemecdn.com/app/element/hamburger.9cf7b091-55e9-11e9-a976-7f4d0b07eef6.png"
                  class="h-[300px] w-full object-cover"
              />
              <template #footer>
                <div class="flex justify-end">
                  <ThumbUpIcon size="30px"/>
                </div>
              </template>
            </t-card>

            <t-card shadow class="[&_.t-card__body]:!p-0">
              <template #header>Yummy hamburger</template>
              <img
                  src="https://shadow.elemecdn.com/app/element/hamburger.9cf7b091-55e9-11e9-a976-7f4d0b07eef6.png"
                  class="h-[300px] w-full object-cover"
              />
              <template #footer>Footer content</template>
            </t-card>
          </div>
        </div>
      </t-content>

      <!--      右边侧边栏    -->
      <div class="overflow-y-auto" :style="{height: scrollHeight}">
        <t-aside :style="{'background-color': bg_color}">
        </t-aside>
      </div>
    </t-layout>
  </t-layout>
</template>

<script setup>
import {computed, ref} from "vue";
import {DialogPlugin, MessagePlugin} from 'tdesign-vue-next';
import {EllipsisIcon, CloseIcon, ThumbUpIcon} from 'tdesign-icons-vue-next';

import MainTopNav from "@/components/MainTopNav.vue";

const MaintopNav = ref(null);

// 滚动高度
const scrollHeight = computed(() => {
  if (MaintopNav.value != null) {
    return window.innerHeight - MaintopNav.value.$el.offsetHeight - 10 + 'px';
  }
  return window.innerHeight - 200 + 'px';
})

const bg_color = computed(() => {
  return process.env["VUE_APP_BG_COLOR "]
})

const openPost = () => {
  const confirmDialog = DialogPlugin.confirm({
    header: '创建帖子',
    body: 'This is a message',
    confirmBtn: '发帖',
    onConfirm: () => {
      MessagePlugin.info('发帖成功');
      confirmDialog.destroy();
    },
  });
}
</script>
