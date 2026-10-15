<template>
  <t-layout>
    <t-header ref="MaintopNav" style="padding: 0;">
      <MainTopNav/>
    </t-header>
    <t-layout style="margin-top: 2px;">
      <!--      左边侧边栏 -->
      <div class="scroll-area" :style="{height: scrollHeight}">
        <t-aside :style="{'background-color': bg_color}">
          <t-menu value="1">
            <t-menu-item value="1">
              <svg t="1722847283965" class="icon" viewBox="0 0 1024 1024" version="1.1"
                   xmlns="http://www.w3.org/2000/svg" p-id="14193" width="28" height="28">
                <path
                    d="M555.541333 117.994667l312.874667 224.565333A117.333333 117.333333 0 0 1 917.333333 437.866667V800c0 64.8-52.533333 117.333333-117.333333 117.333333H640V746.666667c0-70.688-57.312-128-128-128s-128 57.312-128 128v170.666666H224c-64.8 0-117.333333-52.533333-117.333333-117.333333V437.877333a117.333333 117.333333 0 0 1 48.917333-95.317333l312.874667-224.565333a74.666667 74.666667 0 0 1 87.082666 0z"
                    fill="#0089FF" p-id="14194"></path>
              </svg>
              <template #title>首页</template>
            </t-menu-item>
          </t-menu>
          <t-row :gutter="20" style="margin: 0">
            <t-col :span="12" :offset="6">
              <t-button theme="primary" size="large" @click="openPost">发帖</t-button>
            </t-col>
          </t-row>

          <t-divider/>

          <t-row class="text-muted">
            <t-col class="text-center">
              <span>alsoapp &copy;<span id="years_now">&nbsp;{{
                  new Date().getFullYear()
                }}</span>
              </span>
            </t-col>
          </t-row>
        </t-aside>
      </div>
      <!--     内容    -->
      <t-content style="padding: 0;">
        <div class="scroll-area" :style="{height: scrollHeight}">
          <t-row :gutter="20">
            <t-col :span="16" :offset="4">
              <t-card shadow="hover" class="card-flush">
                <template #header>Yummy hamburger</template>
                <img
                    src="https://shadow.elemecdn.com/app/element/hamburger.9cf7b091-55e9-11e9-a976-7f4d0b07eef6.png"
                    style="width: 100%; height: 300px"
                />
                <template #footer>Footer content</template>
              </t-card>
              <br/>
              <t-card shadow="hover" class="card-flush">
                <template #header>
                  <t-row :gutter="20" class="align-items-center">
                    <t-col :span="2" style="margin: 0px; padding: 0px">
                      <t-avatar image="https://cube.elemecdn.com/0/88/03b0d39583f48206768a7534e55bcpng.png" size="large"/>
                    </t-col>
                    <t-col :span="12">
                      <div>test</div>
                      <div>2</div>
                    </t-col>
                    <t-col :span="10" style="display: flex; justify-content: flex-end">
                      <EllipsisIcon/>
                      <CloseIcon/>
                    </t-col>
                  </t-row>
                </template>
                <div>
                  <img
                      src="https://shadow.elemecdn.com/app/element/hamburger.9cf7b091-55e9-11e9-a976-7f4d0b07eef6.png"
                      style="width: 100%; height: 300px"
                  />
                </div>
                <template #footer>
                  <t-row :gutter="20" class="align-items-center">
                    <t-col :span="6" :offset="12">
                      <svg t="1723794882892" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="4275" width="30" height="30"><path d="M939.314286 536.8c19.2-25.371429 29.828571-56.457143 29.828571-88.8 0-51.314286-28.685714-99.885714-74.857143-126.971429a77.337143 77.337143 0 0 0-39.2-10.628571H581.028571l6.857143-140.457143c1.6-33.942857-10.4-66.171429-33.714285-90.742857A121.851429 121.851429 0 0 0 465.142857 41.028571c-59.428571 0-112 40-127.771428 97.257143l-98.171429 355.428572h-0.342857v489.142857h539.771428c10.514286 0 20.8-2.057143 30.285715-6.171429 54.4-23.2 89.485714-76.342857 89.485714-135.314285 0-14.4-2.057143-28.571429-6.171429-42.285715 19.2-25.371429 29.828571-56.457143 29.828572-88.8 0-14.4-2.057143-28.571429-6.171429-42.285714 19.2-25.371429 29.828571-56.457143 29.828572-88.8-0.228571-14.4-2.285714-28.685714-6.4-42.4zM54.857143 530.285714v416c0 20.228571 16.342857 36.571429 36.571428 36.571429h74.285715V493.714286h-74.285715c-20.228571 0-36.571429 16.342857-36.571428 36.571428z" p-id="4276"></path></svg>
                    </t-col>
                  </t-row>
                </template>
              </t-card>
              <br/>
              <t-card shadow="hover" class="card-flush">
                <template #header>Yummy hamburger</template>
                <img
                    src="https://shadow.elemecdn.com/app/element/hamburger.9cf7b091-55e9-11e9-a976-7f4d0b07eef6.png"
                    style="width: 100%; height: 300px"
                />
                <template #footer>Footer content</template>
              </t-card>
            </t-col>
          </t-row>
        </div>
      </t-content>
      <!--      右边侧边栏    -->
      <div class="scroll-area" :style="{height: scrollHeight}">
        <t-aside :style="{'background-color': bg_color}">
        </t-aside>
      </div>
    </t-layout>
  </t-layout>
</template>

<style scoped>
.scroll-area {
  overflow-y: auto;
}

.card-flush :deep(.t-card__body) {
  padding: 0;
}
</style>
<script setup>
import {computed, ref} from "vue";
import {DialogPlugin, MessagePlugin} from 'tdesign-vue-next';
import {EllipsisIcon, CloseIcon} from 'tdesign-icons-vue-next';

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
