import {createRouter, createWebHistory} from 'vue-router';

import HomePage from "@/views/HomePage"
import NotFoundPage from "@/views/NotFoundPage"
import ProductPage from "@/views/ProductPage"
import ResumePage from "@/views/ResumePage"
import SupersetPage from "@/views/SupersetPage"

const routes = [
    { path: '/home', redirect: '/', name: 'home', meta:{ title: "欢迎使用"}},
    { path: '/', component: HomePage, name: 'index', meta:{ title: "欢迎使用"}},
    { path: '/products/superset', component: SupersetPage, name: 'superset', meta:{ title: "superset"}},
    { path: '/products', component: ProductPage, name: 'products', meta:{ title: "产品信息"}},
    { path: '/resumes/:user_id', component: ResumePage, name: 'resumes', meta:{ title: "简历信息"}},
    { path: '/:catchALL(.*)', component: NotFoundPage, name: 'not-fond', meta:{ title: "Not Found"}},
]

const router = createRouter({
    // 内部提供了 history 模式的实现。为了简单起见，我们在这里使用 hash 模式
    history: createWebHistory(),
    routes: routes, // `routes: routes` 的缩写
});

router.beforeEach((to,from,next)=>{//beforeEach是router的钩子函数，在进入路由前执行
    if(to.meta.title){
        document.title = to.meta.title + ' | alsoapp'
    }
    next()  //执行进入路由，如果不写就不会进入目标页
})

export default router;