<template>
  <el-row class="align-items-center px-2" style="background-color: #fff; border-bottom: 2px solid #cbccce">
    <el-col :span="6">
      <img
          style="width: 50px"
          src="https://www.alsoapp.com/favicon.svg"
          alt="you logo"
      />
      <el-input
          placeholder="搜索ap" style="width: 240px" disabled
      />
    </el-col>
    <el-col :span="12">
      <el-menu default-active="1" mode="horizontal" :ellipsis="false"
               background-color="#fff; border-bottom: 2px solid red" @select="handleSelect">
        <div class="flex-grow"></div>
        <el-tooltip content="首页">
          <el-menu-item index="1">
            <el-button text size="large" :auto-insert-space="true" style="width: 120px">
              <template #icon>
                <el-icon :size="80">
                  <svg t="1722845479959" class="icon" viewBox="0 0 1024 1024" version="1.1"
                       xmlns="http://www.w3.org/2000/svg" p-id="7096" width="200" height="200">
                    <path
                        d="M555.541333 117.994667l312.874667 224.565333A117.333333 117.333333 0 0 1 917.333333 437.866667V800c0 64.8-52.533333 117.333333-117.333333 117.333333H640V746.666667c0-70.688-57.312-128-128-128s-128 57.312-128 128v170.666666H224c-64.8 0-117.333333-52.533333-117.333333-117.333333V437.877333a117.333333 117.333333 0 0 1 48.917333-95.317333l312.874667-224.565333a74.666667 74.666667 0 0 1 87.082666 0z"
                        :fill="isActive('1') ? color_select : color" p-id="7097"></path>
                  </svg>
                </el-icon>
              </template>
            </el-button>
          </el-menu-item>
        </el-tooltip>
        <el-tooltip content="正在关注">
          <el-menu-item index="2">
            <el-button text size="large" :auto-insert-space="true" style="width: 120px">
              <template #icon>
                <el-icon :size="80" :color="red">
                  <svg t="1722847185529" class="icon" viewBox="0 0 1024 1024" version="1.1"
                       xmlns="http://www.w3.org/2000/svg" p-id="12993" width="200" height="200">
                    <path
                        d="M939.904 542.08l-224.832 224.768L512 969.92l-266.048-266.048L84.096 542.08c-112.128-112.192-112.128-294.016 0-406.208C140.16 79.744 213.696 51.712 287.232 51.712c73.472 0 147.008 28.032 203.072 84.16L512 157.568l21.696-21.696c112.128-112.192 294.016-112.192 406.208 0 112.128 112.192 112.128 294.016 0 406.208z"
                        :fill="isActive('2') ? color_select : color" p-id="12994"></path>
                  </svg>
                </el-icon>
              </template>
            </el-button>
          </el-menu-item>
        </el-tooltip>
        <el-tooltip content="游戏">
          <el-menu-item index="3">
            <el-button text size="large" :auto-insert-space="true" style="width: 120px">
              <template #icon>
                <el-icon :size="80" :color="red">
                  <svg t="1722847283965" class="icon" viewBox="0 0 1024 1024" version="1.1"
                       xmlns="http://www.w3.org/2000/svg" p-id="14193" width="200" height="200">
                    <path
                        d="M1009.2544 537.2928 1009.2544 434.8928c0-162.9184-114.176-198.9632-187.2896-198.9632L541.9008 235.9296c0.4096-1.536 0.7168-3.2768 0.7168-4.9152l0-65.8432c0-10.3424-8.3968-18.7392-18.7392-18.7392-10.3424 0-18.7392 8.3968-18.7392 18.7392l0 65.8432c0 1.7408 0.2048 3.3792 0.7168 4.9152l-3.8912 0L210.2272 235.9296c-73.1136 0-187.2896 36.0448-187.2896 198.9632l0 102.5024 0 29.9008 0 163.4304c0 59.5968 48.3328 107.9296 107.9296 107.9296 17.408 0 34.816 0 52.1216 0 0 0 58.1632 3.6864 86.016-27.5456 16.5888-18.6368 25.1904-31.8464 25.1904-31.8464 20.5824-27.7504 50.176-41.984 83.968-46.592 7.3728-1.024 14.9504-1.6384 22.4256-1.9456l76.0832 0 129.6384 0c7.4752 0.3072 40.1408 0.9216 47.616 1.9456 33.792 4.608 63.3856 18.8416 83.968 46.592 0 0 8.704 13.2096 25.1904 31.8464 27.8528 31.3344 86.016 27.5456 86.016 27.5456 17.408 0 34.816 0 52.1216 0 59.5968 0 107.9296-48.3328 107.9296-107.9296L1009.152 567.1936 1009.2544 537.2928zM401.2032 510.5664l-114.176 0.3072L286.72 625.2544c0 10.3424-8.3968 18.7392-18.7392 18.7392l0 0c-10.3424 0-18.7392-8.3968-18.7392-18.7392l0.2048-114.2784-114.0736 0.3072 0 0c-10.3424 0-18.7392-8.3968-18.7392-18.7392 0-10.3424 8.2944-18.7392 18.7392-18.7392l114.2784-0.3072 0.2048-114.4832c0-10.3424 8.3968-18.7392 18.7392-18.7392l0 0c10.3424 0 18.7392 8.3968 18.7392 18.7392l-0.2048 114.3808 114.0736-0.3072 0 0c10.3424 0 18.7392 8.3968 18.7392 18.7392C419.9424 502.0672 411.5456 510.464 401.2032 510.5664zM688.2304 488.1408c-31.232 0-56.6272-25.3952-56.6272-56.6272 0-31.232 25.3952-56.5248 56.6272-56.5248s56.6272 25.3952 56.6272 56.5248C744.7552 462.7456 719.4624 488.1408 688.2304 488.1408zM834.56 621.2608c-32.256 0-58.4704-26.2144-58.4704-58.368 0-32.256 26.2144-58.4704 58.4704-58.4704 32.256 0 58.4704 26.2144 58.4704 58.4704C893.0304 595.0464 866.816 621.2608 834.56 621.2608z"
                        :fill="isActive('3') ? color_select : color" p-id="14194"></path>
                  </svg>
                </el-icon>
              </template>
            </el-button>
          </el-menu-item>
        </el-tooltip>
        <div class="flex-grow"></div>
      </el-menu>
    </el-col>
    <el-col :span="6" style="display: flex; justify-content: flex-end;">
      <el-tooltip content="意见反馈">
        <el-button size="large" circle @click="openEmailClient">
          <el-icon size="26">
            <img src="/static/icons/advice.svg" alt="Advice" width="26" height="26"/>
          </el-icon>
        </el-button>
      </el-tooltip>
      <el-tooltip content="账户">
        <el-dropdown trigger="click">
          <el-button circle color="#20B2AA" size="large" style="margin-left: 8px;">test</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item :icon="CircleCheck" divided>退出</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-tooltip>

    </el-col>
  </el-row>
</template>
<style scoped>
.flex-grow {
  flex-grow: 1;
}

.el-menu-item:hover {
  background-color: transparent !important;
}

.el-menu--horizontal > .el-menu-item.is-active {
  border-bottom: 4px solid #0089FF;
}

</style>

<script setup>
import {ref} from "vue";

import {
  ElButton,
  ElCol,
  ElInput,
  ElMenu,
  ElMenuItem,
  ElRow,
  ElIcon,
  ElDropdown,
  ElDropdownMenu,
  ElDropdownItem,
  ElTooltip
} from "element-plus";// 按需引入组件
import {CircleCheck} from '@element-plus/icons-vue' // 按需引入 Icon 图标

// 当前激活的菜单索引
const activeIndex = ref('1');
// 颜色值
const color_select = ref('#0089FF');
const color = ref('#bfbfbf');

// 处理激活状态
function handleSelect(index) {
  activeIndex.value = index;
}

function isActive(index) {
  return activeIndex.value === index;
}

// 打开本地邮箱,发送建议
function openEmailClient() {
  // 这里可以设置收件人、主题、正文等
  // 尝试通过location.href来打开邮件客户端
  // 注意：这可能会被某些浏览器或浏览器设置阻止
  window.location.href = `mailto:mailto:liaozhimingandy@qq.com?subject=建议或意见`;
}
</script>