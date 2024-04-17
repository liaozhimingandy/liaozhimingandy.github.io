<template>
  <el-row class="align-items-center px-2" style="background-color: #fff; border-bottom: 2px solid red">
    <el-col :span="6">
      <img
          style="width: 50px"
          src="https://www.alsoapp.com/favicon.svg"
          alt="you logo"
      />
      <el-input
          placeholder="Please input" style="width: 240px" disabled
      />
    </el-col>
    <el-col :span="12">
      <el-menu default-active="1" mode="horizontal" :ellipsis="false"
               background-color="#fff; border-bottom: 2px solid red">
        <div class="flex-grow"></div>
        <el-tooltip content="首页">
          <el-menu-item index="1">
            <el-icon size="30">
              <House/>
            </el-icon>
          </el-menu-item>
        </el-tooltip>
        <el-tooltip content="朋友">
          <el-menu-item index="2" disabled>朋友</el-menu-item>
        </el-tooltip>
        <el-menu-item index="3" disabled>其它</el-menu-item>
        <div class="flex-grow"></div>
      </el-menu>
    </el-col>
    <el-col :span="6" style="display: flex; justify-content: flex-end;">
      <el-tooltip content="更多">
        <el-button size="large" circle>
          <el-icon size="28">
            <Grid/>
          </el-icon>
        </el-button>
      </el-tooltip>
      <el-tooltip content="账户">
        <el-dropdown trigger="click" disabled>
          <el-button circle color="#20B2AA" size="large" style="margin-left: 8px;">test</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item :icon="Plus">Action 1</el-dropdown-item>
              <el-dropdown-item :icon="CirclePlusFilled">
                Action 2
              </el-dropdown-item>
              <el-dropdown-item :icon="CirclePlus">Action 3</el-dropdown-item>
              <el-dropdown-item :icon="Check">Action 4</el-dropdown-item>
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
</style>

<script setup>
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
import {House, Grid, CircleCheck} from '@element-plus/icons-vue' // 按需引入 Icon 图标
</script>