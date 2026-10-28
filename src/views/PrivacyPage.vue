<template>
  <PageLayout title="隐私政策">
    <div class="mx-auto max-w-4xl">
      <!-- 头部:标题与版本信息 -->
      <div class="mb-6">
        <h1 class="text-2xl font-semibold text-gray-800">隐私政策</h1>
        <p class="mt-2 text-sm text-gray-500">
          更新日期:2026 年 10 月 28 日 · 生效日期:2026 年 10 月 28 日
        </p>
      </div>

      <!-- 概要:一段话说明本站如何处理信息 -->
      <t-card class="mb-6">
        <div class="flex items-start gap-3">
          <ShieldIcon size="24px" fill-color="#0052d9" class="mt-0.5 shrink-0"/>
          <div>
            <h2 class="text-base font-semibold text-gray-800">概要</h2>
            <ul class="mt-2 space-y-1.5 text-sm leading-6 text-gray-600">
              <li class="flex gap-2">
                <CheckCircleIcon size="16px" fill-color="#00a870" class="mt-1 shrink-0"/>
                <span>alsoapp.com 是静态站点，<b class="font-semibold">不提供注册登录，不主动收集您的身份信息</b>;</span>
              </li>
              <li class="flex gap-2">
                <CheckCircleIcon size="16px" fill-color="#00a870" class="mt-1 shrink-0"/>
                <span>托管方 GitHub 与 CDN 服务商 Cloudflare 会记录必要的服务器访问日志，用于安全防护;</span>
              </li>
              <li class="flex gap-2">
                <CheckCircleIcon size="16px" fill-color="#00a870" class="mt-1 shrink-0"/>
                <span>我们使用百度统计了解匿名聚合的页面访问情况，以便改进内容;</span>
              </li>
              <li class="flex gap-2">
                <CheckCircleIcon size="16px" fill-color="#00a870" class="mt-1 shrink-0"/>
                <span>只有您主动发送邮件时，我们才会收到您的邮箱与来信内容;<b class="font-semibold">我们绝不出售、出租您的个人信息</b>。</span>
              </li>
            </ul>
          </div>
        </div>
      </t-card>

      <!-- 目录 -->
      <t-card class="mb-6">
        <h2 class="mb-3 text-base font-semibold text-gray-800">目录</h2>
        <div class="grid grid-cols-1 gap-x-8 gap-y-2 sm:grid-cols-2">
          <a v-for="item in toc" :key="item.id" :href="'#' + item.id"
             class="text-sm text-gray-600 no-underline hover:text-brand">
            {{ item.no }}、{{ item.title }}
          </a>
        </div>
      </t-card>

      <!-- 正文 -->
      <div class="space-y-8 text-sm leading-7 text-gray-700">
        <p>
          alsoapp.com（以下简称「本网站」）是 alsoapp 团队的官方站点，用于展示团队开发的软件产品（如 WeDesk
          远程桌面、「在吗」定时签到 App）及团队信息。我们深知个人信息对您的重要性，将按照法律法规的要求，并参照业界成熟的安全标准，尽力保护您的信息安全。请您仔细阅读本政策，并按照您认为适当的方式作出选择。
        </p>

        <section id="section-1">
          <h2 class="mb-3 text-lg font-semibold text-gray-800">一、我们收集的信息</h2>
          <p class="mb-3">
            本网站为静态站点，不提供账户注册功能，我们不会主动收集您的个人身份信息。仅在以下情形下，您的信息可能被接触或记录：
          </p>
          <div class="space-y-2">
            <p>
              <b class="font-semibold">1、服务器访问日志。</b>
              当您访问本网站时，站点托管服务商 GitHub Pages 与 CDN / 安全防护服务商 Cloudflare
              会自动记录您的 IP 地址、浏览器类型与版本、操作系统、访问时间、请求的页面等日志信息，用于保障服务安全与排查故障。
            </p>
            <p>
              <b class="font-semibold">2、网站流量统计。</b>
              我们使用百度统计了解页面的匿名聚合访问数据（如访问量、来源渠道、页面停留时长），用于改进网站内容与产品介绍。
            </p>
            <p>
              <b class="font-semibold">3、邮件往来。</b>
              当您主动发送邮件至我们的联系邮箱时，我们会收到您的邮箱地址、邮件主题与内容，以及您在邮件中主动提供的其他信息，仅用于回复咨询、处理反馈与必要的售后支持。
            </p>
          </div>
        </section>

        <section id="section-2">
          <h2 class="mb-3 text-lg font-semibold text-gray-800">二、信息的使用</h2>
          <p>我们仅在必要范围内使用上述信息，用于:</p>
          <ul class="mt-2 list-disc space-y-1 pl-6">
            <li>保障本网站的安全、稳定与正常运行;</li>
            <li>分析聚合流量，改进网站内容与产品信息;</li>
            <li>回复您的邮件咨询、处理您的反馈与投诉;</li>
            <li>遵守法律法规及监管要求的其他情形。</li>
          </ul>
        </section>

        <section id="section-3">
          <h2 class="mb-3 text-lg font-semibold text-gray-800">三、Cookie 与同类技术</h2>
          <p>
            本网站自身不设置用于追踪的 Cookie。为提供安全防护与流量统计，Cloudflare
            可能设置安全验证类 Cookie（如 <code class="rounded bg-gray-100 px-1">__cf_bm</code>），百度统计会设置统计类 Cookie。
          </p>
          <p class="mt-2">
            您可以通过浏览器设置清除或拒绝接受 Cookie，这通常不影响您正常浏览本站，但可能导致统计功能失效或安全验证重复出现。
          </p>
        </section>

        <section id="section-4">
          <h2 class="mb-3 text-lg font-semibold text-gray-800">四、信息共享与披露</h2>
          <p>
            我们不会出售、出租或以其他方式将您的个人信息用于商业牟利。仅在以下情形下，我们才可能共享或披露相关信息:
          </p>
          <ul class="mt-2 list-disc space-y-1.5 pl-6">
            <li>
              <b class="font-semibold">服务提供商:</b>
              GitHub（站点托管）、Cloudflare（CDN 与安全防护）、百度统计（流量分析）。上述服务商依据其各自的隐私政策处理数据，我们已与其约定必要的数据保护义务;
            </li>
            <li>
              <b class="font-semibold">法律法规:</b>
              根据法律法规、司法或行政机关的强制性要求提供;
            </li>
            <li>
              <b class="font-semibold">权益保护:</b>
              为维护您、其他用户或公众的生命、财产等重大合法权益所合理必需。
            </li>
          </ul>
        </section>

        <section id="section-5">
          <h2 class="mb-3 text-lg font-semibold text-gray-800">五、数据存储与安全</h2>
          <p>
            本网站部署于 GitHub Pages，服务器日志等数据可能存储于中国境外（如美国）的服务器;数据在网络传输过程中均使用
            HTTPS 加密。我们将尽商业上合理的努力保障信息安全，防止信息遭到未经授权的访问、篡改或泄露。
          </p>
          <p class="mt-2">
            如不幸发生信息安全事件，我们将按照法律法规的要求，及时向您告知事件基本情况、可能的影响、已采取的处置措施及您可自主防范的建议，并通过邮件等方式通知相关用户。
          </p>
          <p class="mt-2">
            请您理解:互联网并非绝对安全的环境，通过邮件等渠道交流时，请妥善保护自己的敏感信息，仅在必要情形下提供。
          </p>
        </section>

        <section id="section-6">
          <h2 class="mb-3 text-lg font-semibold text-gray-800">六、第三方服务与外部链接</h2>
          <p>
            本网站可能包含指向第三方网站或服务的链接。该等第三方服务由相关方独立运营，其信息处理活动不适用本政策，而是适用第三方自己的隐私声明，我们建议您仔细阅读其条款。
          </p>
          <p class="mt-2">
            本政策适用于 alsoapp.com 网站本身。对于 WeDesk、「在吗」等独立应用产品，其个人信息处理规则以相应应用内另行公布的隐私政策为准。
          </p>
        </section>

        <section id="section-7">
          <h2 class="mb-3 text-lg font-semibold text-gray-800">七、未成年人保护</h2>
          <p>
            我们高度重视未成年人个人信息保护。若您是未成年人，请在监护人的陪同下阅读本政策并使用本网站;监护人有权对未成年人的相关信息进行查询、更正与删除。若我们在不知情的情况下收集了未成年人信息，将尽快删除。
          </p>
        </section>

        <section id="section-8">
          <h2 class="mb-3 text-lg font-semibold text-gray-800">八、隐私政策的更新</h2>
          <p>
            我们可能适时修订本政策。对于重大变更，我们将通过本页面公布修订后的政策，并在页面顶部更新「更新日期」。修订生效后您继续使用本网站，即表示同意受修订后政策的约束。
          </p>
        </section>

        <section id="section-9">
          <h2 class="mb-3 text-lg font-semibold text-gray-800">九、如何联系我们</h2>
          <p>
            如您对本政策有任何疑问、意见或投诉，或希望行使查询、更正、删除您的个人信息等权利，请通过以下方式与我们联系:
          </p>

          <!-- 联系方式卡片 -->
          <t-card class="mt-4">
            <div class="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div class="flex items-center gap-3">
                <t-avatar size="44px" class="!bg-brand/10">
                  <MailIcon size="22px" fill-color="#0052d9"/>
                </t-avatar>
                <div>
                  <p class="text-sm font-semibold text-gray-800">alsoapp 团队</p>
                  <t-link theme="primary" href="mailto:contact@alsoapp.com" class="text-base">
                    contact@alsoapp.com
                  </t-link>
                </div>
              </div>
              <t-button theme="primary" href="mailto:contact@alsoapp.com?subject=隐私政策咨询">
                <template #icon>
                  <MailIcon/>
                </template>
                发送邮件
              </t-button>
            </div>
          </t-card>
          <p class="mt-3 text-gray-600">
            为保障安全，在处理涉及您个人信息的请求前，我们可能需要先核实您的身份。我们将在收到请求后的
            <b class="font-semibold">15 个工作日</b>内核实并回复。
          </p>
        </section>
      </div>
    </div>
  </PageLayout>
</template>

<script setup>
import {
  MailIcon,
  ShieldIcon,
  CheckCircleIcon,
} from 'tdesign-icons-vue-next';

// 目录数据:点击可平滑滚动到对应章节
const toc = [
  {id: 'section-1', no: '一', title: '我们收集的信息'},
  {id: 'section-2', no: '二', title: '信息的使用'},
  {id: 'section-3', no: '三', title: 'Cookie 与同类技术'},
  {id: 'section-4', no: '四', title: '信息共享与披露'},
  {id: 'section-5', no: '五', title: '数据存储与安全'},
  {id: 'section-6', no: '六', title: '第三方服务与外部链接'},
  {id: 'section-7', no: '七', title: '未成年人保护'},
  {id: 'section-8', no: '八', title: '隐私政策的更新'},
  {id: 'section-9', no: '九', title: '如何联系我们'},
];
</script>
