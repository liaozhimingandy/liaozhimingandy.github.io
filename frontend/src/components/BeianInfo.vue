<script setup lang="ts">
/**
 * 网站备案信息（公安备案 + ICP 备案），按法规展示在网站底部。
 *
 * 两个备案号均链接到官方查询平台：
 *  - 公安备案：全国公安机关互联网安全管理服务平台（beian.mps.gov.cn）
 *  - ICP 备案：工信部 ICP/IP 地址/域名信息备案管理系统（beian.miit.gov.cn）
 *
 * 这是静态站点公示信息，不需要 env 配置；首页与门户页脚共用同一组件，
 * 避免两处硬编码导致备案号变更时漏改。颜色继承父级，便于不同页脚复用。
 */
const POLICE_RECORD = '粤公网安备44030002019954号'
const POLICE_URL = 'https://beian.mps.gov.cn/#/query/webSearch?code=44030002019954'
const ICP_RECORD = '粤ICP备2026175415号-1'
const ICP_URL = 'https://beian.miit.gov.cn/'
</script>

<template>
  <span class="beian-info">
    <a
      :href="POLICE_URL"
      target="_blank"
      rel="noopener noreferrer"
      class="beian-link"
    >{{ POLICE_RECORD }}</a>
    <span class="beian-sep">&nbsp;&nbsp;|&nbsp;&nbsp;</span>
    <a
      :href="ICP_URL"
      target="_blank"
      rel="noopener noreferrer"
      class="beian-link"
    >{{ ICP_RECORD }}</a>
  </span>
</template>

<style scoped>
.beian-info {
  font-size: 12px;
  line-height: 1.6;
}
.beian-link {
  color: inherit;
  text-decoration: none;
}
.beian-link:hover {
  color: var(--color-brand, #0052d9);
}
.beian-sep {
  opacity: 0.6;
}
</style>
