<template>
  <div class="flex h-screen w-screen flex-col bg-white">
    <iframe
        v-if="resume"
        :src="resume"
        :title="`${user_id} 的简历`"
        class="w-full flex-1 border-0"
    ></iframe>
  </div>
</template>

<script setup>
import {ref, computed} from "vue";
import {useRoute} from 'vue-router'
import router from "@/router";

const route = useRoute();

// 当前用户id
const user_id = ref('');

// 简历列表
const resumes = {
  "liaozhiming": "/static/resumes/liaozhiming.html"
};

// 当前显示简历
const resume = computed(() => resumes[user_id.value]);

// 取url中的参数,不存在则跳 404
user_id.value = route.params.user_id;
if (!resume.value) {
  router.push("/not-found/");
}
</script>
