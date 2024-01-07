<template>
  <iframe ref="iframe" :src="resume" :height="fullHeight" :width="fullWidth"></iframe>
</template>

<script setup>
import {ref, onMounted, onUnmounted, reactive, computed} from "vue";
import { useRoute } from 'vue-router'
import router from "@/router";

const route = useRoute();

// iframe高度
const fullHeight = ref(0);
const fullWidth = ref(0);
// 当前用户id
const user_id = ref('');

// 简历列表
const resumes = reactive({
  "taobao": "http://www.taobao.com",
  "liaozhiming": "/static/liaozhiming.html"
});

// 当前显示简历
const resume = computed(() => {
  return resumes[user_id.value]});

// 窗口变化时处理逻辑
function handleResize(){
  var offsetHeigth = document.querySelector("#app").clientHeight-document.querySelector("iframe").clientHeight;
  // var offsetWidth = document.querySelector("#app").clientWidth-document.querySelector("iframe").clientWidth;
  fullHeight.value = window.innerHeight-offsetHeigth;
  fullWidth.value = window.innerWidth-20;
}

// 组件挂载时处理逻辑
onMounted(() => {
   // 取url中的参数
   user_id.value = route.params.user_id;
   if(!(user_id.value in resumes)){
     router.push("/not-found");
  }
   handleResize();
   window.addEventListener('resize', handleResize);
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
})

</script>

<style scoped>

</style>