<template>
  <PageLayout title="Superset">
    <h4 class="mb-3 text-xl font-semibold">可视化-Superset</h4>

    <!-- 轮播 -->
    <t-swiper :duration="3000" :interval="5000" class="mb-4">
      <t-swiper-item v-for="(item, index) in items.carousels" :key="index">
        <div class="relative">
          <img :src="item.image_src" :alt="item.alt" class="h-72 w-full object-cover"/>
          <div class="absolute inset-x-0 bottom-0 bg-black/40 p-4 text-white">
            <h5 class="text-lg font-semibold">{{ item.title }}</h5>
            <p class="text-sm">{{ item.text }}</p>
          </div>
        </div>
      </t-swiper-item>
    </t-swiper>

    <h5 class="pt-2 text-lg font-semibold">项目案例</h5>
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <t-card
          v-for="(item, index) in items.templates"
          :key="index"
          :bordered="true"
          header-bordered
          :title="item.title"
      >
        <template #title>
          <span class="font-semibold">{{ item.title }}</span>
        </template>
        <img :src="item.image_src" :alt="item.alt" class="h-40 w-full object-cover"/>
        <p class="pt-2 text-sm text-gray-500">{{ item.text }}</p>
      </t-card>
    </div>
  </PageLayout>
</template>

<script setup>
import {reactive} from "vue";
import PageLayout from "@/components/PageLayout.vue";

const items = reactive({
  "carousels": [
    {
      "image_src": "/static/superset/superset-explore.jpg",
      "alt": "探索",
      "title": "探索",
      "text": "使用数据可视化数组浏览数据"
    },
    {
      "image_src": "/static/superset/superset-dashboard.jpg",
      "alt": "视图",
      "title": "视图",
      "text": "通过交互式仪表板查看数据"
    },
    {
      "image_src": "/static/superset/superset-sql_lab.jpg",
      "alt": "sql 实验室",
      "title": "sql 实验室",
      "text": "使用 SQL 实验室编写查询以浏览数据."
    },
    {
      "image_src": "/static/superset/case09.jpg",
      "alt": "项目案例",
      "title": "项目案例",
      "text": "上市公司全景概览"
    }
  ],
  "templates": [
    {
      "image_src": "/static/superset/tpl03.jpg",
      "alt": "大屏模板",
      "title": "大屏模板",
      "text": "大屏模板-1"
    },
    {
      "image_src": "/static/superset/case08.jpg",
      "alt": "树图",
      "title": "项目案例",
      "text": "树图"
    },
    {
      "image_src": "/static/superset/case07.jpg",
      "alt": "项目案例-上市公司地域分布",
      "title": "项目案例",
      "text": "项目案例-上市公司地域分布"
    },
    {
      "image_src": "/static/superset/tpl03.jpg",
      "alt": "大屏模板",
      "title": "大屏模板",
      "text": "大屏模板-1"
    }
  ]
});
</script>
