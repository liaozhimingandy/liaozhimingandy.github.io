<template>
  <div class="text-bg-dark p-3 text-center">
    Superset<B>&nbsp;&bull;&nbsp;</B><span class="text-center"><a href="mailto:liaozhimingandy@qq.com"
                                                                  class="text-light" style="text-decoration: none;"
                                                                  data-bs-toggle="tooltip" data-bs-placement="top"
                                                                  data-bs-custom-class="custom-tooltip"
                                                                  data-bs-title="通过邮件联系我们;邮箱地址: liaozhimingandy@qq.com">联系我们</a></span>
  </div>
  <div class="container pt-3">
    <h4>可视化-Superset</h4>
    <div class="row">
      <div id="carouselExampleCaptions" class="carousel carousel-dark slide" data-bs-ride="carousel">
        <div class="carousel-inner">
          <div class="carousel-item" v-for="(item, index) in items.carousels" :key="index" :class="{'active': !index}">
            <img :src="item.image_src" class="d-block w-100 h-50" :alt="item.alt"/>
            <div class="carousel-caption d-none d-md-block">
              <h5>{{ item.title }}</h5>
              <p>{{ item.text }}</p>
            </div>
          </div>

        </div>
        <button class="carousel-control-prev" type="button" data-bs-target="#carouselExampleCaptions"
                data-bs-slide="prev"><span class="carousel-control-prev-icon" aria-hidden="true"></span> <span
            class="visually-hidden">Previous</span></button>
        <button class="carousel-control-next" type="button" data-bs-target="#carouselExampleCaptions"
                data-bs-slide="next"><span class="carousel-control-next-icon" aria-hidden="true"></span> <span
            class="visually-hidden">Next</span></button>
      </div>
    </div>

    <h5 class="pt-2">项目案例</h5>
    <div class="row row-cols-md-4">

      <div class="col" v-for="(item, index) in items.templates" :key="index">
        <div class="card" style="width: 20rem;">
          <img :src="item.image_src" class="card-img-top" :alt="item.alt"/>
          <div class="card-body">
            <h5 class="card-title">{{ item.title }}</h5>
            <p class="card-text">{{ item.text }}</p>
          </div>
        </div>
      </div>

    </div>

    <!-- 版权信息 -->
    <CopyRight />
  </div>
</template>

<script setup>
import {reactive} from "vue";
import CopyRight from "@/components/CopyRight";


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

<style scoped>

</style>