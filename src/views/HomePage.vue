<template>
  <div :style="backgroundStyle">
    <nav class="navbar sticky-top bg-light border-bottom border-body" :class="navBgClass">
      <div class="container">
        <a class="navbar-brand" href="/">
          <img src="https://www.alsoapp.com/favicon.svg" alt="alsoapp" width="30" height="24">
        </a>
        <span class="navbar-text">
               <a href="mailto:liaozhimingandy@qq.com" class="text-muted">意见反馈</a>
            </span>
      </div>
    </nav>
    <br>
    <div class="container">
      <div class="alert alert-warning alert-dismissible fade show" role="alert" :class="navBgClass">
        <strong>
          <router-link :to="{'name': 'products'}" class="text-muted">更多</router-link>
        </strong>
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
      </div>

      <div class="card mt-2" v-for="(item, index) in links" :key="index" :class="[item.border_clss,navBgClass]">
        <h6 class="card-header">
          {{ item.title }}({{ item.data.length }})
        </h6>
        <div class="card-body">
          <div class="row row-cols-auto g-3">
            <div class="col" v-for="(link, item_index) in item.data" :key="item_index"><a :href="link.href"
                                                                                          class="text-muted"
                                                                                          style="text-decoration: none;"
                                                                                          target="_blank"><h6>
              {{ link.title }}</h6>
            </a>
            </div>
          </div>
        </div>
      </div>
      <!-- 卡片图片 -->
      <div class="row mt-0 row-cols-auto g-2">
        <div class="col">
          <div class="card" :class="navBgClass">
            <h6 class="card-header">
              请联系我们,我们很乐意为你服务!
            </h6>
            <div class="card-body">
              <img src="/static/contact-us-wechat.jpg" alt="联系方式" class="card-img-top" height="400px"
                   @click="imageHandleClick" data-bs-toggle="modal"
                   data-bs-target="#myModal"/>
            </div>
          </div>
        </div>
        <div class="col">
          <div class="card" :class="navBgClass">
            <h6 class="card-header">
              支付宝红包T-1
            </h6>
            <div class="card-body">
              <img src="/static/red-packet-tjy.png" alt="支付宝红包" height="400rem" class="card-img-top"
                   @click="imageHandleClick" data-bs-toggle="modal"
                   data-bs-target="#myModal"/>
            </div>
          </div>
        </div>
        <div class="col">
          <div class="card" :class="navBgClass">
            <h6 class="card-header">
              支付宝红包-2
            </h6>
            <div class="card-body">
              <img src="/static/red-packet-me.png" alt="支付宝红包" height="400rem" class="card-img-top"
                   data-bs-toggle="modal"
                   data-bs-target="#myModal" @click="imageHandleClick"/>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 模态框 -->
    <div class="modal fade" id="myModal" tabindex="-1" role="dialog" aria-labelledby="myModalLabel" aria-hidden="true">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h1 class="modal-title fs-5" id="staticBackdropLabel">{{ modal_data.header_modal }}</h1>
            <button type="button" class="btn-close btn btn-danger" data-bs-dismiss="modal" aria-label="Close"></button>
          </div>
          <div class="modal-body text-center">
            <img :src="modal_data.image_src_modal" alt="image" height="400px">
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-primary" data-bs-dismiss="modal">确认</button>
          </div>
        </div>
      </div>
    </div>

    <CopyRight></CopyRight>
  </div>
</template>

<script setup>
import {computed, reactive, ref} from "vue";
import CopyRight from "@/components/CopyRight";

// 模态弹框
const modal_data = reactive({"image_src_modal": "/static/red-packet-me.png", "header_modal": ""});

// 链接
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
        "href": "https://wx.qq.com/",
        "title": "网页版微信"
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
        "title": "Boss直聘"
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
      },
      {
        "title": "数据库排名榜",
        "href": "https://db-engines.com/en/ranking"
      }
    ]
  }
]);

// 图片点击处理
const imageHandleClick = (e) => {
  modal_data.image_src_modal = e.target.src;
  modal_data.header_modal = e.target.alt;
};

// 当前时间设置为东八区
const currentDateKey = computed(() =>{
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

// 是否背景透明
let navBgClass = ref('');
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
    navBgClass = 'bg-transparent';
    return {
      backgroundImage: `url(${holidayImage.value})`,
      backgroundSize: 'contain',
      backgroundPosition: 'center',
    }
  } else {
    return null
  }

})
</script>

<style scoped>
.col > a > h6:hover {
  color: red;
}
</style>