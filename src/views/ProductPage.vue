<template>
  <div class="text-bg-dark p-3 text-center">Demo<B>&nbsp;•&nbsp;</B><span class="text-center"><a
      href="mailto:liaozhimingandy@qq.com" class="text-light" style="text-decoration: none;" data-bs-toggle="tooltip"
      data-bs-placement="top" data-bs-custom-class="custom-tooltip"
      data-bs-title="通过邮件联系我们;邮箱地址: liaozhimingandy@qq.com">联系我们</a>
      </span>
  </div>

  <!--内容-->
  <div class="container content pt-2">
    <h6>部分</h6>
    <hr>
    <div class="row align-items-start">
      <div class="col col-lg-3 col-6" v-for="(product, index) in products.main" :key="index">
        <div class="clearfix">
          <img class="img-thumbnail" style="width:60px; height: 60px;"
               :src="product.image_src" alt="..."  data-src="holder.js/60x60">
          <span><a :href="product.href" style="text-decoration: none;">{{ product.title }}</a></span>
        </div>
      </div>
    </div>
    <h6 class="pt-4">其它工具</h6>
    <hr>
    <div class="row align-items-start">
      <div class="col col-lg-3 col-6" v-for="(product, index) in products.other" :key="index">
        <div class="clearfix">
          <img class="img-thumbnail" style="width:60px; height: 60px;"
               :src="product.image_src" alt="..." data-src="holder.js/60x60">
          <span><a :href="product.href" style="text-decoration: none;">{{ product.title }}</a></span>
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

 // data to display
 const products = reactive(
     {
       "main": [
           {
         "title": "Superset",
         "href": "/products/superset/",
         "image_src": "https://www.alsoapp.com/assets/images/superset.svg",
         "lable": ""
       }
       ],
       "other":[{
         "title": "Rhapsody官方文档",
         "href": "https://www.alsoapp.com/docs-rhapsody/6.9.1/?lang=en",
         "image_src": "https://www.alsoapp.com/assets/images/rhapsody.svg",
         "lable": ""
       },
         {
         "title": "Rhapsody笔记",
         "href": "https://www.alsoapp.com/docs-note-rhapsody/",
         "image_src": "https://www.alsoapp.com/assets/images/note.svg",
         "lable": ""
       }
       ]
     }
 )

</script>

<style scoped>

</style>