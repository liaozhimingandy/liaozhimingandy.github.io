import { createApp } from 'vue'
import App from './App.vue'

// Tailwind CSS 工具类
import '@/assets/tailwind.css';
// TDesign 组件样式
import 'tdesign-vue-next/es/style/index.css'

// 引入路由隐射表
import router from "@/router";

createApp(App).use(router).mount('#app')
