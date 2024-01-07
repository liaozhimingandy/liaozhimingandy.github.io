import { createApp } from 'vue'
import App from './App.vue'

// 引入bootstrap,外网下使用cdn加速
import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap/dist/js/bootstrap.min.js';

// 引入路由隐射表
import router from "@/router";

createApp(App).use(router).mount('#app')
