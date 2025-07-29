import {createRouter, createWebHistory} from 'vue-router';

import HomePage from "@/views/HomePage"
import NotFoundPage from "@/views/NotFoundPage"
import ProductPage from "@/views/ProductPage"
import ResumePage from "@/views/ResumePage"
import SupersetPage from "@/views/SupersetPage"
import PrivacyView from "@/views/PrivacyPage.vue";
import TestPage from "@/views/TestPage.vue";
import IndexPage from "@/views/hipmessageservice/IndexPage.vue";
import ServicePage from "@/views/hipmessageservice/ServicePage.vue";
import CDAPage from "@/views/hipmessageservice/CDAPage.vue";
import DictPage from "@/views/hipmessageservice/DictPage.vue";
import LoginPage from "@/views/LoginPage.vue";

const routes = [
    {path: '/home', redirect: '/', name: 'home', meta: {title: "欢迎使用"}},
    {path: '/', component: HomePage, name: 'index', meta: {title: "欢迎使用"}},
    {path: '/products/superset', component: SupersetPage, name: 'superset', meta: {title: "superset"}},
    {path: '/products/', component: ProductPage, name: 'products', meta: {title: "产品信息"}},
    {path: '/resumes/:user_id/', component: ResumePage, name: 'resumes', meta: {title: "简历信息"}},
    {
        path: '/hipmessageservice/',
        name: 'hipmessageservice',
        component: IndexPage,
        redirect: '/hipmessageservice/service/',
        children: [
            {
                path: 'service/', component: ServicePage, name: 'hipmessageservice-service', meta: {title: "互联互通标准服务"}
            },
            {
                path: 'cda/', component: CDAPage, name: 'hipmessageservice-cda', meta: {title: "互联互通标准CDA"}
            },
            {
                path: 'dict/', component: DictPage, name: 'hipmessageservice-dict', meta: {title: "互联互通标准值域参考"}
            }
        ]
    },
    {path: '/privacy/', component: PrivacyView, name: 'privacy'},
    {path: '/test/', component: TestPage, name: 'test'},
    {path: '/login/', component: LoginPage, name: 'login'},
    {path: '/:catchALL(.*)/', component: NotFoundPage, name: 'not-fond', meta: {title: "Not Found"}},
]

const router = createRouter({
    // 内部提供了 history 模式的实现。为了简单起见，我们在这里使用 hash 模式
    history: createWebHistory(),
    routes: routes, // `routes: routes` 的缩写
    trailingSlash: true // 设置 URL 以斜杠结尾
});

router.beforeEach((to, from, next) => {//beforeEach是router的钩子函数，在进入路由前执行
    if (to.meta.title) {
        document.title = to.meta.title + ' | alsoapp'
    }

    // 如果路径不是以 / 开头，则自动添加 /
    if (!to.path.endsWith('/')) {
        next({path: to.path + '/'});
    } else {
        next();
    }
})

export default router;