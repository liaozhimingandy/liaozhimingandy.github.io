<template>
  <div :style="backgroundStyle">
    <nav class="sticky top-0 z-10 border-b border-gray-200 bg-gray-50">
      <div class="mx-auto flex max-w-7xl items-center justify-between px-4 py-2">
        <router-link to="/">
          <img src="https://www.alsoapp.com/favicon.svg" alt="alsoapp" width="30" height="24">
        </router-link>
        <span>
          <t-link theme="default" hover="color" href="mailto:contact@alsoapp.com">意见反馈</t-link>
        </span>
      </div>
    </nav>

    <div class="mx-auto max-w-7xl px-4 pt-6">
      <t-alert theme="warning" :close="true" class="mb-4">
        <template #message>
          <router-link :to="{'name': 'products'}" class="text-gray-500 hover:text-brand">更多</router-link>
        </template>
      </t-alert>

      <!-- 常用链接卡片 -->
      <t-card
          v-for="(item, index) in links"
          :key="index"
          :title="`${item.title}(${item.data.length})`"
          :bordered="true"
          class="mb-4"
          header-bordered
      >
        <template #title>
          <span class="text-base font-semibold">{{ item.title }}({{ item.data.length }})</span>
        </template>
        <div class="flex flex-wrap gap-4">
          <a
              v-for="(link, item_index) in item.data"
              :key="item_index"
              :href="link.href"
              target="_blank"
              class="text-base text-gray-600 no-underline hover:text-red-500"
          >{{ link.title }}</a>
        </div>
      </t-card>

      <!-- 卡片图片 -->
      <div class="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <t-card
            v-for="(card, index) in cards"
            :key="index"
            :title="card.title"
            :bordered="true"
            header-bordered
        >
          <template #title>
            <span class="text-base font-semibold">{{ card.title }}</span>
          </template>
          <img
              :src="card.src"
              :alt="card.title"
              class="h-[400px] w-full cursor-pointer object-contain"
              @click="imageHandleClick"
          />
        </t-card>
      </div>
    </div>

    <!-- 图片查看弹窗 -->
    <t-dialog
        v-model:visible="dialogVisible"
        :header="modal_data.header_modal"
        :footer="false"
        width="600px"
        placement="center"
    >
      <div class="text-center">
        <img :src="modal_data.image_src_modal" alt="image" class="mx-auto h-[400px] object-contain">
      </div>
    </t-dialog>

    <CopyRight/>
  </div>
</template>

<script setup>
import {computed, reactive, ref} from "vue";
import CopyRight from "@/components/CopyRight";

// 图片弹窗数据
const modal_data = reactive({"image_src_modal": "/static/red-packet-me.png", "header_modal": ""});
// 弹窗是否显示
const dialogVisible = ref(false);

// 底部三张卡片
const cards = [
  {title: "请联系我们,我们很乐意为你服务!", src: "/static/contact-us-wechat.jpg"},
  {title: "支付宝红包T-1", src: "/static/red-packet-tjy.png"},
  {title: "支付宝红包-2", src: "/static/red-packet-me.png"},
];

// 链接
const links = reactive([
  {
    "title": " 常用网站",
    "data": [
      {"href": "https://www.baidu.com", "title": "百度"},
      {"href": "https://map.baidu.com/", "title": "百度地图"},
      {"href": "https://yiyan.baidu.com/", "title": "百度文心一言"},
      {"href": "https://weibo.com/", "title": "新浪微博"},
      {"href": "https://jd.com/", "title": "京东"},
      {"href": "https://taobao.com/", "title": "淘宝"},
      {"href": "https://wx.qq.com/", "title": "网页版微信"},
      {"href": "https://filehelper.weixin.qq.com/", "title": "微信文件传输助手"},
      {"href": "https://www.12306.cn/index/", "title": "12306"},
      {"href": "https://www.bilibili.com/", "title": "哔哩哔哩"},
      {"href": "https://www.douyin.com/", "title": "抖音"},
      {"href": "https://music.163.com/", "title": "网易云音乐"},
      {"href": "https://www.chsi.com.cn/", "title": "学信网"}
    ]
  },
  {
    "title": " AI类",
    "data": [
      {"href": "https://chatgpt.com/", "title": "ChatGPT"},
      {"href": "https://chat.baidu.com/", "title": "DeepSeek"}
    ]
  },
  {
    "title": " 招聘网站",
    "data": [
      {"href": "https://www.51job.com/", "title": "前程无忧"},
      {"href": "https://www.liepin.com/", "title": "猎聘"},
      {"href": "https://www.zhaopin.com/", "title": "智联招聘"},
      {"href": "https://www.zhipin.com/", "title": "Boss直聘"}
    ]
  },
  {
    "title": " 工具类网站",
    "data": [
      {"href": "https://jsonhero.io/", "title": "json格式化视图"},
      {"href": "https://tool.oschina.net/codeformat/xml", "title": "在线xml格式校验"},
      {"href": "https://smallpdf.com/cn/merge-pdf", "title": "pdf操作工具"},
      {"title": "数据库排名榜", "href": "https://db-engines.com/en/ranking"},
      {"title": "图标工厂", "href": "https://icon.wuruihong.com/"}
    ]
  }
]);

// 图片点击处理
const imageHandleClick = (e) => {
  modal_data.image_src_modal = e.target.src;
  modal_data.header_modal = e.target.alt;
  dialogVisible.value = true;
};

// 当前时间设置为东八区
const currentDateKey = computed(() => {
  // 时区设置
  const options = {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  };
  const dateKey = new Date().toLocaleString('zh-CN', options);
  return dateKey.split('T')[0].replace(/\//g, '').substring(4, 8);
});

// 节假日列表
const holidays = reactive({
  "0308": "https://t8.baidu.com/it/u=171130374,479106205&fm=193",
  "0501": "https://appwk.baidu.com/naapi/doc/view?ih=810&o=jpg_6&iw=1440&ix=0&iy=0&aimw=1440&rn=1&doc_id=285a303e77eeaeaad1f34693daef5ef7bb0d12c4&pn=1&sign=97a39ffbc0c719b2321805dd81cdc63e&type=1&app_ver=2.9.8.2&ua=bd_800_800_IncredibleS_2.9.8.2_2.3.7&bid=1&app_ua=IncredibleS&uid=&cuid=&fr=3&Bdi_bear=WIFI&from=3_10000&bduss=&pid=1&screen=800_800&sys_ver=2.3.7",
  "0209": "https://picnew13.photophoto.cn/20190107/chuangyikatongchuxibeijinghechenghaibao-32419333_1.jpg",
  "0210": "https://img0.baidu.com/it/u=855279891,19405313&fm=253&fmt=auto&app=138&f=JPEG?w=800&h=500"
});

// 获取节假日对应图片
const holidayImage = computed(() => {
  // 检查当前日期是否在节假日对象中
  return holidays[currentDateKey.value];
});

// 计算html背景样式
const backgroundStyle = computed(() => {
  if (holidayImage.value) {
    return {
      backgroundImage: `url(${holidayImage.value})`,
      backgroundSize: 'contain',
      backgroundPosition: 'center',
    }
  }
  return null
})
</script>
