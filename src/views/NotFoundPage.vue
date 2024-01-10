<template>
    <section class="w3l-errorpage">
    <div class="error404">
        <div class="wrapper">
            <div class="logo-brand">
                <h1><a class="brand-logo-text">404
                    <div class="position-head"><span>E</span>rror
                    </div></a></h1>

                <!-- if logo is image enable this
                <a class="brand-logo" href="#index.html">
                    <img src="image-path" alt="Your logo" title="Your logo" style="height:35px;" />
                </a> -->
            </div>
        </div>
        <div class="wrapper">
            <div class="midle-page">
                <section class="error-container">
                    <span><span>4</span></span>
                    <span>0</span>
                    <span><span>4</span></span>
                </section>
                <h1>Page Not Found</h1>
                <p class="zoom-area para">对不起，页面丢失了，请返回首页或者联系我们哦 </p>
                <div class="link-container text-center">
                    <router-link :to="{'name': 'index'}" class="more-link">返回首页</router-link>
                </div>
            </div>
            <div class="columns-copy">
                 <CopyRight/>
            </div>
        </div>
    </div>
</section>
</template>

<script setup>

import CopyRight from "@/components/CopyRight";
</script>

<style scoped>

.wrapper {
    width: 100%;
    padding-right: 15px;
    padding-left: 15px;
    margin-right: auto;
    margin-left: auto;
}

@media (min-width: 576px) {
    .wrapper {
        max-width: 540px;
    }
}

@media (min-width: 768px) {
    .wrapper {
        max-width: 720px;
    }
}

@media (min-width: 992px) {
    .wrapper {
        max-width: 960px;
    }
}

@media (min-width: 1200px) {
    .wrapper {
        max-width: 1140px;
    }
}

button,
input,
select {
    -webkit-appearance: none;
    outline: none;
}

ul li {
    display: block;
}

a {
    text-decoration: none;
}

iframe {
    border: none;
}

ul {
    margin: 0;
    padding: 0;
}

p, a, ul li, input, span, button, textarea {
    font-family: -apple-system-font, BlinkMacSystemFont, Microsoft YaHei, Microsoft YaHei UI, Helvetica Neue, PingFang SC, Hiragino Sans GB, Arial, sans-serif;
    margin: 0;
    padding: 0;
}

figure {
    margin: 0;
}

a img {
    display: block;
}

h1 a.brand-logo-text {
    color: #fff;
    font-weight: 600;
    font-size: 45px;
    line-height: 55px;
    margin-bottom: 2px;
    display: inline-block;
    font-family: 'Quicksand', sans-serif;
}

.logo-brand {
    max-width: 500px;
    margin: 0 0 0 auto;
    text-align: left;
}

.position-head {
    position: relative;
    display: inline;
    margin-left: 20px;
}

.position-head span {
    position: absolute;
    width: 40px;
    text-align: left;
    left: -20%;
    top: 5px;
    color: red;
    transform: rotate(21deg);
    font-family: 'Quicksand', sans-serif;
}

.columns-copy p {
    font-size: 16px;
    line-height: 25px;
    color: #000;
    max-width: 500px;
    margin: 35px 0 0 auto;
    text-align: center;
}

.columns-copy p a {
    font-size: 16px;
    line-height: 25px;
    color: #ff0000;
}

.columns-copy p a:hover {
    text-decoration: underline;
    color: #ff0000;
}

p.para {
    font-size: 16px;
    line-height: 25px;
    color: #777;
}

ul.social li,
ul.jst-link li {
    display: inline-block;
    margin-right: 5px;
}

ul.social li a {
    font-size: 16px;
    line-height: 25px;
    color: #bbb;
}

ul.social li a span {
    font-size: 20px;
    background: #ffffff;
    width: 35px;
    height: 35px;
    line-height: 36px;
    text-align: center;
    border-radius: 50%;
}

@media all and (max-width: 1080px) {
    .main-tatile-txt h3 {
        font-size: 37px;
        line-height: 47px;
    }

    .main-tatile-txt h3 span {
        font-size: 45px;
    }

}

@media all and (max-width: 768px) {
    .main-tatile-txt h3 {
        font-size: 33px;
        line-height: 43px;
    }

    .main-tatile-txt h3 span {
        font-size: 43px;
    }
}

@media all and (max-width: 480px) {
    .just-logo {
        padding: 20px 0 20px;
    }

    .main-tatile-txt h3 span {
        font-size: 40px;
    }

    .main-tatile-txt h3 {
        font-size: 30px;
    }
}

@media all and (max-width: 441px) {
}

/* demo stuff */
/*--responsive--*/
/*--//responsive--*/
.w3l-errorpage .error-container {
    font-size: 120px;
    line-height: 130px;
    font-weight: 800;
    margin: 0 0 40px;
}

.w3l-errorpage .error404 {
  background: url('../assets/404.jpg') no-repeat center;
  background-size: cover;
    -webkit-background-size: cover;
    -moz-background-size: cover;
    -o-background-size: cover;
    -ms-background-size: cover;
    z-index: 1;
    display: grid;
    position: relative;
    align-items: center;
    min-height: 100vh;
    padding: 40px 0;
}

/* .w3l-errorpage .error404:before { */
/* content: ""; */
/* background: rgba(0, 0, 0, 0.78); */
/* width: 100%; */
/* position: absolute; */
/* top: 0px; */
/* bottom: 0px; */
/* opacity: .6; */
/* z-index: -1; } */
.w3l-errorpage .error-container > span {
    display: inline-block;
    line-height: 0.7;
    position: relative;
    color: #3be8b0;
}

.w3l-errorpage .error-container > span > span {
    display: inline-block;
    position: relative;
}

.w3l-errorpage .error-container > span:nth-of-type(1) {
    perspective: 800px;
    perspective-origin: 50% 50%;
    color: #39eafd;
}

.w3l-errorpage .error-container > span:nth-of-type(1) > span {
    transform-origin: 0 60%;
    transform: rotate(0);
    -webkit-animation: easyoutelastic 10s infinite;
    animation: easyoutelastic 10s infinite;
    transition-delay: 3s;
}

.w3l-errorpage .error-container > span:nth-of-type(3) {
    perspective: 800px;
    perspective-origin: 50% 50%;
    color: #ee70a6;
}

.w3l-errorpage .error-container > span:nth-of-type(3) > span {
    transform-origin: 0 60%;
    transform: rotate(0);
    -webkit-animation: easyoutelastic 10s infinite;
    animation: easyoutelastic 10s infinite;
    transition-delay: 3s;
}

@-webkit-keyframes easyoutelastic {
    0% {
        transform: rotateX(0deg);
    }
    9% {
        transform: rotateX(0deg);
    }
    13% {
        transform: rotateX(180deg);
    }
    16% {
        transform: rotateX(180deg);
    }
    18% {
        transform: rotateX(170deg);
    }
    20% {
        transform: rotateX(200deg);
    }
    60% {
        transform: rotateX(150deg);
    }
    80% {
        transform: rotateX(210deg);
    }
    100% {
        transform: rotateX(0deg);
    }
}

@keyframes easyoutelastic {
    0% {
        transform: rotateX(0deg);
    }
    9% {
        transform: rotateX(0deg);
    }
    13% {
        transform: rotateX(180deg);
    }
    16% {
        transform: rotateX(180deg);
    }
    18% {
        transform: rotateX(170deg);
    }
    20% {
        transform: rotateX(200deg);
    }
    60% {
        transform: rotateX(150deg);
    }
    80% {
        transform: rotateX(210deg);
    }
    100% {
        transform: rotateX(0deg);
    }
}

.w3l-errorpage * {
    box-sizing: border-box;
}

.w3l-errorpage .zoom-area {
    margin: 15px auto 15px;
}

.w3l-errorpage a.more-link {
    text-transform: capitalize;
    font-size: 13px;
    background-color: #0a0a0a;
    padding: 10px 15px;
    color: #fff;
    display: inline-block;
    line-height: 1.5;
    text-decoration: none;
    letter-spacing: 1px;
    margin-top: 30PX;
}

.w3l-errorpage a.more-link:hover {
    background-color: red;
}

.w3l-errorpage .error404 h1 {
    font-size: 40px;
    line-height: 50px;
}

.w3l-errorpage .midle-page {
    max-width: 500px;
    margin: 0 0 0 auto;
    background: #f9f9f9;
    padding: 40px 40px;
}

@media (max-width: 991px) {
    .w3l-errorpage .logo-brand {
        margin: 0 auto;
    }

    .w3l-errorpage .midle-page {
        margin: 0 auto;
    }

    .columns-copy p {
        margin: 35px auto 0;
        text-align: center;
    }
}

@media (max-width: 800px) {
    .w3l-errorpage .error404 h1 {
        font-size: 35px;
    }

    .w3l-errorpage .midle-page {
        padding: 30px 24px;
    }

    .w3l-errorpage .error-container {
        margin: 0 0 35px;
        font-size: 100px;
        line-height: 110px;
    }
}

@media (max-width: 440px) {
    .w3l-errorpage .error404 h1 {
        font-size: 30px;
    }

    .w3l-errorpage .zoom-area {
        margin: 10px auto 10px;
        font-size: 16px;
    }

    .w3l-errorpage .error-container {
        font-size: 100px;
        line-height: 110px;
        margin: 20px 0;
    }
}

@media (max-width: 384px) {
    h1 a.brand-logo-text {
        font-size: 35px;
        line-height: 45px;
    }
}
</style>