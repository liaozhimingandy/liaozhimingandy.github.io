<template>
  <t-row class="align-items-center px-2" style="background-color: #fff; border-bottom: 2px solid red">
    <t-col :span="6">
      <img
          style="width: 50px"
          src="https://www.alsoapp.com/favicon.svg"
          alt="you logo"
      />
      <t-input
          placeholder="Please input" style="width: 240px" disabled
      />
    </t-col>
    <t-col :span="12">
      <t-menu value="1" mode="horizontal">
        <t-menu-item value="1">
          <t-tooltip content="首页">
            <t-button variant="text" size="large" style="width: 120px">
              <HomeIcon size="28px"/>
            </t-button>
          </t-tooltip>
        </t-menu-item>
        <t-menu-item value="2" disabled>朋友</t-menu-item>
        <t-menu-item value="3" disabled>其它</t-menu-item>
      </t-menu>
    </t-col>
    <t-col :span="6" style="display: flex; justify-content: flex-end;">
      <t-tooltip content="更多">
        <t-button shape="circle" size="large">
          <ViewModuleIcon size="24px"/>
        </t-button>
      </t-tooltip>
      <t-tooltip content="账户">
        <t-dropdown
            trigger="click"
            disabled
            :options="accountOptions"
            maxColumnWidth="140"
        >
          <t-button shape="circle" size="large" style="margin-left: 8px; background-color: #20B2AA; color: #fff;">
            test
          </t-button>
        </t-dropdown>
      </t-tooltip>
    </t-col>
  </t-row>
</template>
<style scoped>
.t-menu--horizontal .t-menu__item .t-button {
  padding: 0;
}

.t-menu--horizontal .t-menu__item.t-is-active {
  border-bottom: 4px solid blue;
}
</style>

<script setup>
import {HomeIcon, ViewModuleIcon} from 'tdesign-icons-vue-next' // 按需引入 Icon 图标

// 账户下拉菜单
const accountOptions = [
  {content: 'Action 1', value: 'action1'},
  {content: 'Action 2', value: 'action2'},
  {content: 'Action 3', value: 'action3'},
  {content: 'Action 4', value: 'action4'},
  {content: '退出', value: 'logout', divider: true}
];
</script>
