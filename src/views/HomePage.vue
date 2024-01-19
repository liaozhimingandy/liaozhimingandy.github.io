<template>
  <nav class="navbar sticky-top bg-light border-bottom border-body">
    <div class="container">
      <a class="navbar-brand" href="/">
        <img src="https://www.alsoapp.com/favicon.svg" alt="alsoapp" width="30" height="24">
      </a>
      <span class="navbar-text">
                此网站维护中... 你可以提供宝贵的意见或建议;<a href="mailto:liaozhimingandy@qq.com" class="text-muted">点击此处打开邮箱客户端用于发送邮件</a>
            </span>
    </div>
  </nav>
  <br>
  <div class="container">
    <div class="alert alert-warning alert-dismissible fade show" role="alert">
      <strong>
        <router-link :to="{'name': 'products'}" class="text-muted">更多</router-link>
      </strong>
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    </div>

    <div class="card mt-2" v-for="(item, index) in links" :key="index" :class="item.border_clss">
      <h6 class="card-header">
        {{ item.title }}
      </h6>
      <div class="card-body">
        <div class="row">
          <div class="col col-auto" v-for="(link, item_index) in item.data" :key="item_index"><a :href="link.href"
                                                                                                 class="text-muted"
                                                                                                 style="text-decoration: none;"
                                                                                                 target="_blank"><h6>
            {{ link.title }}</h6>
          </a>
          </div>
        </div>
      </div>
    </div>

    <div class="card mt-2" style="width: 25rem;">
      <h6 class="card-header">
        请联系我们,我们很乐意为你服务!
      </h6>
      <div class="card-bod">
        <img src="/static/contact-us-wechat.jpg" height="400px"/>
      </div>
    </div>
  </div>

  <CopyRight></CopyRight>

</template>

<script setup>

import {reactive} from "vue";
import CopyRight from "@/components/CopyRight";

const links = reactive([
  {
    "title": " 常用网站",
    "border_clss": "border-primary",
    "class": "mian",
    "data": [
      {
        "href": "https://www.baidu.com",
        "title": "百度"
      },
      {
        "href": "https://map.baidu.com/",
        "title": "百度地图"
      },
      {
        "href": "https://yiyan.baidu.com/",
        "title": "百度文心一言"
      },
      {
        "href": "https://weibo.com/",
        "title": "新浪微博"
      },
      {
        "href": "https://jd.com/",
        "title": "京东"
      },
      {
        "href": "https://taobao.com/",
        "title": "淘宝"
      },
      {
        "href": "https://filehelper.weixin.qq.com/",
        "title": "微信文件传输助手"
      },
      {
        "href": "https://www.12306.cn/index/",
        "title": "12306"
      },
      {
        "href": "https://www.bilibili.com/",
        "title": "哔哩哔哩"
      },
      {
        "href": "https://www.douyin.com/",
        "title": "抖音"
      },
      {
        "href": "https://music.163.com/",
        "title": "网易云音乐"
      },
      {
        "href": "https://www.chsi.com.cn/",
        "title": "学信网"
      }
    ]
  },
  {
    "title": " 招聘网站",
    "border_clss": "border-success",
    "class": "jobs",
    "data": [
      {
        "href": "https://www.51job.com/",
        "title": "前程无忧"
      },
      {
        "href": "https://www.liepin.com/",
        "title": "猎聘"
      },
      {
        "href": "https://www.zhaopin.com/",
        "title": "智联招聘"
      },
      {
        "href": "https://www.zhipin.com/",
        "title": "boss直聘"
      }
    ]
  },
  {
    "title": " 工具类网站",
    "border_clss": "border-warning",
    "class": "tools",
    "data": [
      {
        "href": "https://www.json.cn/",
        "title": "在线json格式校验"
      },
      {
        "href": "https://tool.oschina.net/codeformat/xml",
        "title": "在线xml格式校验"
      },
      {
        "href": "https://smallpdf.com/cn/merge-pdf",
        "title": "pdf操作工具"
      }
    ]
  }
])

</script>

<style scoped>
.col > a > h6:hover {
  color: red;
}
</style>