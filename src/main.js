import { createApp } from 'vue'
import App from './App.vue'

import { createPinia } from "pinia";
// 引入bootstrap,外网下使用cdn加速
import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap/dist/js/bootstrap.min.js';
import 'element-plus/dist/index.css' // 引入样式

// 引入路由隐射表
import router from "@/router";

createApp(App).use(router).use(createPinia()).mount('#app')
