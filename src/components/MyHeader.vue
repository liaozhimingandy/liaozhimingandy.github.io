<template>
  <div class="flex items-center gap-3 px-3 border-b-2 border-red-500 bg-white">
    <div class="flex flex-1 items-center gap-2">
      <img class="w-[50px]" src="https://www.alsoapp.com/favicon.svg" alt="you logo"/>
      <t-input class="w-60" placeholder="Please input" disabled/>
    </div>

    <div class="flex-[2]">
      <t-menu class="border-0" value="1" mode="horizontal">
        <t-menu-item value="1">
          <t-tooltip content="首页">
            <t-button variant="text" size="large">
              <HomeIcon size="28px"/>
            </t-button>
          </t-tooltip>
        </t-menu-item>
        <t-menu-item value="2" disabled>朋友</t-menu-item>
        <t-menu-item value="3" disabled>其它</t-menu-item>
      </t-menu>
    </div>

    <div class="flex flex-1 items-center justify-end gap-2">
      <t-tooltip content="更多">
        <t-button shape="circle" size="large">
          <ViewModuleIcon size="24px"/>
        </t-button>
      </t-tooltip>
      <t-tooltip content="账户">
        <t-dropdown trigger="click" disabled :options="accountOptions" maxColumnWidth="140">
          <t-button shape="circle" size="large" class="!bg-[#20B2AA] !text-white">test</t-button>
        </t-dropdown>
      </t-tooltip>
    </div>
  </div>
</template>

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
