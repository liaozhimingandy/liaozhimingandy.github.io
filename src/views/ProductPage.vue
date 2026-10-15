<template>
  <div class="sticky top-0 z-10 bg-gray-800 px-3 py-3 text-center text-white">
    Demo<B>&nbsp;&bull;&nbsp;</B>
    <MyTooltip/>
  </div>

  <!--内容-->
  <div class="mx-auto max-w-7xl px-4 pt-2" v-for="(item, index) in products" :key="index">
    <h6 class="mb-2 text-base font-semibold">{{ item.label }}</h6>
    <hr class="mb-3">
    <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <div
          v-for="(product, item_index) in item.data"
          :key="item_index"
          class="flex items-center gap-2 rounded p-2 hover:ring-2 hover:ring-red-500"
      >
        <img class="h-[60px] w-[60px] rounded border border-gray-200" :src="product.image_src" :alt="product.label"/>
        <router-link
            v-if="product.to"
            :to="{'name': product.to}"
            class="text-gray-700 no-underline hover:text-brand"
        >{{ product.title }}
        </router-link>
        <t-link v-else theme="default" hover="color" :href="product.href">{{ product.title }}</t-link>
      </div>
    </div>
  </div>

  <!-- 版权信息 -->
  <CopyRight/>
</template>

<script setup>
import {reactive} from "vue";
import CopyRight from "@/components/CopyRight";
import MyTooltip from "@/components/MyTooltip";

// data to display
const products = reactive(
    [
      {
        "category": "main",
        "label": "部分",
        "data": [
          {
            "title": "Superset",
            "href": "/products/superset/",
            "to": "superset",
            "image_src": "/static/superset.svg",
            "label": "superset"
          },
          {
            "title": "Rhapsody",
            "href": "https://www.alsoapp.com/docs-rhapsody/6.9.1/en/the-rhapsody-platform.html",
            "to": "",
            "image_src": "/static/rhapsody.svg",
            "label": "Rhapsody"
          }
        ]
      },
      {
        "category": "other",
        "label": "其它工具",
        "data": [
          {
            "title": "Rhapsody官方文档",
            "href": "https://www.alsoapp.com/docs-rhapsody-7.1/?lang=en",
            "image_src": "/static/rhapsody.svg",
            "label": "Rhapsody官方文档"
          },
          {
            "title": "Rhapsody笔记",
            "href": "https://www.alsoapp.com/docs-note-rhapsody/",
            "image_src": "/static/note.svg",
            "label": "Rhapsody笔记"
          }
        ]
      },
      {
        "category": "hipmessage",
        "label": "医院信息平台互联互通相关",
        "data": [
          {
            "title": "医院信息平台交互规范",
            "href": "/hipmessageservice/",
            "image_src": "/static/note.svg",
            "label": "医院信息平台交互规范"
          }
        ]
      }
    ]
)
</script>
