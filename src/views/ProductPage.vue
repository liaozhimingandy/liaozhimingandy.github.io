<template>
  <div class="text-bg-dark p-3 text-center" sticky-top>Demo<B>&nbsp;•&nbsp;</B><span class="text-center">
    <MyTooltip></MyTooltip>
      </span>
  </div>

  <!--内容-->
  <div class="container content pt-2" v-for="(item, index) in products" :key="index">
    <h6>{{ item.label }}</h6>
    <hr>
    <div class="row align-items-start">
      <div class="col col-lg-3 col-6" v-for="(product, item_index) in item.data" :key="item_index">
        <div class="clearfix rounded">
          <img class="img-thumbnail m-1" style="width:60px; height: 60px;"
               :src="product.image_src" alt="{{ product.label }}" data-src="holder.js/60x60">
        <router-link v-if="product.to" :to="{'name': product.to}"  style="text-decoration: none;"> {{
              product.title
            }}</router-link>
          <a v-else :href="product.href"  style="text-decoration: none;"> {{
              product.title
            }}</a>
        </div>
      </div>
    </div>
  </div>

  <!-- 版权信息 -->
  <CopyRight></CopyRight>
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
                "href": "https://www.alsoapp.com/docs-rhapsody/6.9.1/?lang=en",
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
    }
]
)

</script>

<style scoped>
.clearfix:hover {
  border: 2px solid red;
}
</style>