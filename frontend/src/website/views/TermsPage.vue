<template>
  <PageLayout title="服务条款">
    <div class="mx-auto max-w-4xl">
      <!-- 头部:标题与版本信息 -->
      <div class="mb-6">
        <h1 class="text-2xl font-semibold text-gray-800">服务条款</h1>
        <p class="mt-2 text-sm text-gray-500">
          更新日期:2026 年 11 月 23 日 · 生效日期:2026 年 11 月 23 日
        </p>
      </div>

      <!-- 概要 -->
      <t-card class="mb-6">
        <div class="flex items-start gap-3">
          <CheckCircleIcon size="24px" fill-color="#00a870" class="mt-0.5 shrink-0"/>
          <div>
            <h2 class="text-base font-semibold text-gray-800">概要</h2>
            <ul class="mt-2 space-y-1.5 text-sm leading-6 text-gray-600">
              <li class="flex gap-2">
                <CheckCircleIcon size="16px" fill-color="#00a870" class="mt-1 shrink-0"/>
                <span>alsoapp.com 提供「按现状」的免费在线服务与应用导航;<b class="font-semibold">服务可用性不作承诺</b>,可能因维护、故障等原因中断;</span>
              </li>
              <li class="flex gap-2">
                <CheckCircleIcon size="16px" fill-color="#00a870" class="mt-1 shrink-0"/>
                <span>您使用本站产品与服务时,应遵守所在地区法律法规,<b class="font-semibold">不得用于任何违法或侵害他人权益的用途</b>;</span>
              </li>
              <li class="flex gap-2">
                <CheckCircleIcon size="16px" fill-color="#00a870" class="mt-1 shrink-0"/>
                <span>数据保护与个人信息处理,详见<a :href="privacyHref" class="text-brand hover:underline">《隐私政策》</a>;</span>
              </li>
              <li class="flex gap-2">
                <CheckCircleIcon size="16px" fill-color="#00a870" class="mt-1 shrink-0"/>
                <span>在法律允许的最大范围内,我们对因使用本站产生的<b class="font-semibold">间接损失不承担责任</b>;</span>
              </li>
              <li class="flex gap-2">
                <CheckCircleIcon size="16px" fill-color="#00a870" class="mt-1 shrink-0"/>
                <span>本条款可能适时更新,更新后将在本页发布并标注生效日期。</span>
              </li>
            </ul>
          </div>
        </div>
      </t-card>

      <!-- 正文:目录式章节 -->
      <t-card class="mb-6">
        <template #title>
          <span class="text-base font-semibold">条款正文</span>
        </template>

        <h2 id="section-1" class="mt-4 text-base font-semibold text-gray-800">一、服务说明</h2>
        <p class="mt-2 text-sm leading-6 text-gray-600">
          alsoapp.com(下称"本站")是 Also Apps 的官方站点,提供产品介绍、应用导航与在线工具服务。
          本站的部分能力(如锦囊 SafeKeep 的云端同步)依赖第三方基础设施(GitHub、Cloudflare 等),
          相应服务可能受其服务状态影响。
        </p>

        <h2 id="section-2" class="mt-6 text-base font-semibold text-gray-800">二、账号与安全</h2>
        <p class="mt-2 text-sm leading-6 text-gray-600">
          需要登录的服务统一使用 Also Account(Logto)认证。您应妥善保管账号凭据,并对账号下的操作负责。
          发现账号被盗用时,请及时通过 contact@alsoapp.com 与我们联系。
        </p>

        <h2 id="section-3" class="mt-6 text-base font-semibold text-gray-800">三、用户行为规范</h2>
        <p class="mt-2 text-sm leading-6 text-gray-600">
          您承诺不利用本站从事危害国家安全、泄露国家秘密、侵犯他人合法权益的活动;
          不上传、传播含有违法、侵权内容的信息;不对本站进行恶意攻击、爬取或干扰其正常运行。
        </p>

        <h2 id="section-4" class="mt-6 text-base font-semibold text-gray-800">四、知识产权</h2>
        <p class="mt-2 text-sm leading-6 text-gray-600">
          本站的页面设计、文案、图标与代码,除注明开源许可的部分外,均归本站所有。
          未经书面许可,不得复制、转载或用于商业用途。
        </p>

        <h2 id="section-5" class="mt-6 text-base font-semibold text-gray-800">五、免责声明</h2>
        <p class="mt-2 text-sm leading-6 text-gray-600">
          本站内容仅作参考,不构成任何专业建议。对于因不可抗力、第三方服务中断、
          您的误操作等原因造成的损失,本站不承担责任。
        </p>

        <h2 id="section-6" class="mt-6 text-base font-semibold text-gray-800">六、联系我们</h2>
        <p class="mt-2 text-sm leading-6 text-gray-600">
          对本条款有任何疑问,请联系 <a href="mailto:contact@alsoapp.com" class="text-brand hover:underline">contact@alsoapp.com</a>。
        </p>
      </t-card>
    </div>
  </PageLayout>
</template>

<script setup>
import {computed} from "vue";
import PageLayout from "@/website/components/PageLayout.vue";
import {CheckCircleIcon} from 'tdesign-icons-vue-next';

// 隐私政策内链(history 模式带尾斜杠,与路由表保持一致)
const privacyHref = computed(() => '/privacy/');
</script>
