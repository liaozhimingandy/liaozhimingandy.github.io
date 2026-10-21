<template>
  <PageLayout title="WeDesk">
    <!-- 首屏 -->
    <section
        class="mb-10 rounded-lg bg-gradient-to-br from-[#0b1b3a] via-[#123a7a] to-[#0052d9] px-6 py-12 text-white sm:px-10 sm:py-16"
    >
      <div class="grid items-center gap-8 lg:grid-cols-2">
        <div>
          <t-tag theme="primary" variant="light" class="mb-4">远程桌面 · 免费可用</t-tag>
          <h1 class="mb-3 text-3xl font-bold leading-tight sm:text-4xl">WeDesk 远程桌面</h1>
          <p class="mb-6 text-base text-white/80 sm:text-lg">
            4K 原画 · 60 帧流畅 · 毫秒级延迟。<br/>
            随时随地，安全连接你的电脑、服务器与移动设备。
          </p>
          <div class="flex flex-wrap items-center gap-3">
            <t-button theme="primary" size="large" @click="onDownload">
              <template #icon>
                <DownloadIcon/>
              </template>
              免费下载
            </t-button>
            <t-button theme="default" variant="outline" size="large" @click="onContact">
              <template #icon>
                <UsergroupIcon/>
              </template>
              了解企业版
            </t-button>
          </div>
          <p class="mt-4 text-sm text-white/60">当前系统：Windows · 个人版永久免费 · 无需注册即可连接</p>
        </div>

        <!-- 远程窗口示意 -->
        <div class="hidden lg:block">
          <div class="overflow-hidden rounded-lg bg-white/10 p-3 backdrop-blur">
            <div class="mb-2 flex items-center gap-1.5">
              <span class="h-2.5 w-2.5 rounded-full bg-red-400"></span>
              <span class="h-2.5 w-2.5 rounded-full bg-yellow-400"></span>
              <span class="h-2.5 w-2.5 rounded-full bg-green-400"></span>
              <span class="ml-2 text-xs text-white/70">WeDesk - 远程主机</span>
            </div>
            <div class="grid grid-cols-3 gap-2">
              <div
                  v-for="i in 9"
                  :key="i"
                  class="h-16 rounded bg-white/20"
                  :class="i % 4 === 0 ? 'bg-white/35' : ''"
              ></div>
            </div>
            <div class="mt-3 flex items-center justify-between text-xs text-white/70">
              <span class="flex items-center gap-1">
                <ThunderIcon size="14px"/> 延迟 {{ metrics.latency }}
              </span>
              <span class="flex items-center gap-1">
                <Screen4KIcon size="14px"/> {{ metrics.quality }}
              </span>
              <span class="flex items-center gap-1">
                <WifiIcon size="14px"/> 已加密
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 性能数据 -->
      <div class="mt-10 grid grid-cols-2 gap-4 border-t border-white/20 pt-8 sm:grid-cols-4">
        <div v-for="(m, index) in metricList" :key="index">
          <div class="text-2xl font-bold sm:text-3xl">{{ m.value }}</div>
          <div class="mt-1 text-sm text-white/70">{{ m.label }}</div>
        </div>
      </div>
    </section>

    <!-- 核心技术 -->
    <section class="mb-10">
      <h2 class="mb-1 text-center text-2xl font-bold">自研传输架构，为远控而生</h2>
      <p class="mb-6 text-center text-sm text-gray-500">从编解码到网络选路全链路自研，弱网也能稳定流畅</p>
      <div class="grid gap-4 md:grid-cols-3">
        <t-card v-for="(tech, index) in technologies" :key="index" :bordered="true" header-bordered>
          <template #title>
            <div class="flex items-center gap-2">
              <component :is="tech.icon" size="22px" fill-color="#0052d9"/>
              <span class="font-semibold">{{ tech.title }}</span>
            </div>
          </template>
          <p class="text-sm leading-6 text-gray-600">{{ tech.desc }}</p>
        </t-card>
      </div>
    </section>

    <!-- 全平台支持 -->
    <section class="mb-10">
      <h2 class="mb-6 text-center text-2xl font-bold">全平台覆盖，一处登录处处可达</h2>
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <div
            v-for="(p, index) in platforms"
            :key="index"
            class="flex flex-col items-center gap-2 rounded-lg border border-gray-200 py-5 hover:border-brand hover:text-brand"
        >
          <component :is="p.icon" size="28px"/>
          <span class="text-sm">{{ p.name }}</span>
        </div>
      </div>
    </section>

    <!-- 核心功能 -->
    <section class="mb-10">
      <h2 class="mb-6 text-center text-2xl font-bold">核心功能</h2>
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <t-card v-for="(f, index) in features" :key="index" :bordered="true">
          <div class="flex items-start gap-3">
            <div class="rounded bg-brand/10 p-2 text-brand">
              <component :is="f.icon" size="20px"/>
            </div>
            <div>
              <h3 class="mb-1 text-base font-semibold">{{ f.title }}</h3>
              <p class="text-sm leading-6 text-gray-600">{{ f.desc }}</p>
            </div>
          </div>
        </t-card>
      </div>
    </section>

    <!-- 使用场景 -->
    <section class="mb-10">
      <h2 class="mb-6 text-center text-2xl font-bold">深入不同场景，解决真实问题</h2>
      <t-tabs v-model="activeScene" class="mb-4">
        <t-tab-panel v-for="(s, index) in scenes" :key="index" :value="index" :label="s.name">
          <div class="rounded-lg bg-gray-50 p-5">
            <p class="mb-3 text-sm text-gray-600">{{ s.summary }}</p>
            <ul class="space-y-2">
              <li v-for="(point, pIndex) in s.points" :key="pIndex" class="flex items-start gap-2 text-sm text-gray-700">
                <CheckCircleIcon size="16px" fill-color="#00a870" class="mt-0.5 shrink-0"/>
                <span>{{ point }}</span>
              </li>
            </ul>
          </div>
        </t-tab-panel>
      </t-tabs>
    </section>

    <!-- 安全保障 -->
    <section class="mb-10">
      <h2 class="mb-6 text-center text-2xl font-bold">多层安全保障，连接可管可控</h2>
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div
            v-for="(s, index) in securities"
            :key="index"
            class="rounded-lg border border-gray-200 p-4"
        >
          <component :is="s.icon" size="24px" fill-color="#00a870"/>
          <h3 class="mb-1 mt-2 text-base font-semibold">{{ s.title }}</h3>
          <p class="text-sm leading-6 text-gray-600">{{ s.desc }}</p>
        </div>
      </div>
    </section>

    <!-- 版本对比 -->
    <section class="mb-10">
      <h2 class="mb-6 text-center text-2xl font-bold">选择适合你的版本</h2>
      <div class="grid gap-4 md:grid-cols-3">
        <t-card
            v-for="(plan, index) in plans"
            :key="index"
            :bordered="true"
            header-bordered
            :class="plan.recommended ? 'ring-2 ring-brand' : ''"
        >
          <template #title>
            <div class="flex items-center justify-between">
              <span class="font-semibold">{{ plan.name }}</span>
              <t-tag v-if="plan.recommended" theme="primary" size="small">推荐</t-tag>
            </div>
          </template>
          <div class="mb-3 text-2xl font-bold text-brand">{{ plan.price }}</div>
          <ul class="space-y-2">
            <li v-for="(item, iIndex) in plan.items" :key="iIndex" class="flex items-start gap-2 text-sm text-gray-600">
              <CheckCircleIcon size="16px" fill-color="#00a870" class="mt-0.5 shrink-0"/>
              <span>{{ item }}</span>
            </li>
          </ul>
          <t-button block class="mt-4" :theme="plan.recommended ? 'primary' : 'default'" variant="outline">
            {{ plan.action }}
          </t-button>
        </t-card>
      </div>
    </section>

    <!-- 常见问题 -->
    <section class="mb-10">
      <h2 class="mb-6 text-center text-2xl font-bold">常见问题</h2>
      <t-collapse v-model="activeFaq">
        <t-collapse-panel v-for="(f, index) in faqs" :key="index" :value="index" :header="f.q">
          <p class="text-sm leading-6 text-gray-600">{{ f.a }}</p>
        </t-collapse-panel>
      </t-collapse>
    </section>

    <!-- 底部引导 -->
    <section
        class="rounded-lg bg-gradient-to-r from-[#0052d9] to-[#4086ff] px-6 py-10 text-center text-white"
    >
      <h2 class="mb-2 text-2xl font-bold">现在开始，免费远程你的第一台设备</h2>
      <p class="mb-5 text-sm text-white/80">安装包不到 20MB，一分钟完成安装与连接</p>
      <div class="flex flex-wrap justify-center gap-3">
        <t-button theme="default" size="large" @click="onDownload">
          <template #icon>
            <DownloadIcon/>
          </template>
          下载 WeDesk
        </t-button>
        <t-button theme="default" variant="outline" size="large" @click="onContact">
          <template #icon>
            <QrcodeIcon/>
          </template>
          联系我们
        </t-button>
      </div>
    </section>
  </PageLayout>
</template>

<script setup>
import {ref} from "vue";
import {MessagePlugin} from "tdesign-vue-next";
import PageLayout from "@/components/PageLayout.vue";
import {
  DownloadIcon,
  UsergroupIcon,
  ThunderIcon,
  Screen4KIcon,
  WifiIcon,
  MobileIcon,
  ServerIcon,
  TerminalIcon,
  CloudIcon,
  ControlPlatformIcon,
  SwapIcon,
  PrintIcon,
  LockOnIcon,
  UsbIcon,
  ScreenMirroringIcon,
  SoundIcon,
  FileSafetyIcon,
  VerifiedIcon,
  DashboardIcon,
  QrcodeIcon,
  CheckCircleIcon,
  LogoWindowsIcon,
  LogoAppleIcon,
  LogoAndroidIcon,
  LogoChromeIcon,
} from 'tdesign-icons-vue-next';

// 当前激活的场景 Tab
const activeScene = ref(0);
// 当前展开的常见问题
const activeFaq = ref([0]);

// 首屏窗口示意中的实时指标
const metrics = {
  latency: '8ms',
  quality: '4K 60fps'
};

// 性能数据
const metricList = [
  {value: '<10ms', label: '端到端平均延迟'},
  {value: '60fps', label: '最高画面帧率'},
  {value: '40%', label: '带宽利用率提升'},
  {value: '30%', label: '丢包无感阈值'},
];

// 核心技术
const technologies = [
  {
    icon: ThunderIcon,
    title: 'WeLink 传输引擎',
    desc: '自研 RTC 传输引擎，毫秒级低延迟架构，端到端延迟稳定控制在 10ms 以内，操作响应如同本地。'
  },
  {
    icon: ControlPlatformIcon,
    title: '自适应编解码',
    desc: '支持 H.264 / AV1 编码与 4:4:4 真彩模式，弱网自动降码率保流畅，强网自动拉满画质与帧率。'
  },
  {
    icon: CloudIcon,
    title: '边缘加速网络',
    desc: '全球加速节点就近接入，智能选路绕开拥堵链路，拥塞率下降约 90%，跨地域连接同样稳定。'
  },
];

// 支持平台
const platforms = [
  {name: 'Windows', icon: LogoWindowsIcon},
  {name: 'macOS', icon: LogoAppleIcon},
  {name: 'Linux', icon: TerminalIcon},
  {name: 'Android', icon: LogoAndroidIcon},
  {name: 'iOS / iPadOS', icon: MobileIcon},
  {name: '网页版', icon: LogoChromeIcon},
];

// 核心功能
const features = [
  {icon: Screen4KIcon, title: '多屏控制', desc: '自动识别全部副屏，支持单屏切换与全景同显，超宽屏比例自适应不拉伸。'},
  {icon: SwapIcon, title: '文件传输', desc: '拖拽即传，支持批量勾选、断点续传与快捷路径，大文件传输稳定不中断。'},
  {icon: PrintIcon, title: '远程打印', desc: '把远端文件直接输出到身边打印机，异地办公也能立刻拿到纸质件。'},
  {icon: LockOnIcon, title: '隐私屏', desc: '一键让被控端黑屏并锁死键鼠，防止他人旁观，保护敏感操作过程。'},
  {icon: ServerIcon, title: '无人值守', desc: '绑定设备后随时接入，配合远程唤醒实现巡检、升级、排障全程自动化。'},
  {icon: UsbIcon, title: '外设映射', desc: '数位板、游戏手柄、U 盘、摄像头等外设重定向到远端，压感与多点触控同样可用。'},
  {icon: ScreenMirroringIcon, title: '屏幕标注', desc: '远程演示时用画笔在屏幕上圈画批注，配合多指针让沟通更直观。'},
  {icon: SoundIcon, title: '声音同步', desc: '远端声音与本地麦克风双向同步，语音沟通与影音监听都不掉线。'},
  {icon: TerminalIcon, title: '远程终端', desc: '无需图形界面时直接发起命令行终端，维护服务器快且几乎不占带宽。'},
];

// 使用场景
const scenes = [
  {
    name: '远程办公',
    summary: '在家或出差也能完整使用公司电脑的性能与资料。',
    points: [
      '4K 原画画质与超低延时，写文档、敲代码、做设计都精准跟手',
      '文件不出公司设备，TB 级素材随时调用，保护数字资产',
      '外出也能远程运行工作站上的大型程序，笔记本不再是性能瓶颈'
    ]
  },
  {
    name: 'IT 运维',
    summary: '设备批量部署与统一管理，提前预警风险。',
    points: [
      '命令行静默部署，一条命令完成安装与账号绑定',
      '设备分组、标签管理与上下线消息推送，状态一手掌握',
      '后台批量下发文件与补丁，显著降低运维工作量'
    ]
  },
  {
    name: '技术支持',
    summary: '快速响应客户问题，无需到场即可排障。',
    points: [
      '生成网页链接发给客户，点击即可接入，沟通成本极低',
      '支持多开窗口，同时处理多位客户的请求',
      '内置聊天窗口与云端录屏，处理过程完整留档'
    ]
  },
  {
    name: '远程教学',
    summary: '把屏幕变成课堂，演示与指导同步完成。',
    points: [
      '画笔批注与多指针功能，讲解重点一目了然',
      '手机 / 平板也能作为主控端，随时随地开展指导',
      '临时密码 + 一次性授权，课后即刻失效，安全可控'
    ]
  },
];

// 安全保障
const securities = [
  {icon: FileSafetyIcon, title: '端到端加密', desc: '连接全程高强度加密，密钥不落服务端，第三方无法解密。'},
  {icon: VerifiedIcon, title: '新设备验证', desc: '陌生设备登录需手机二次确认，即使密码泄露也无法接入。'},
  {icon: LockOnIcon, title: '临时密码', desc: '生成一次性连接密码，用完自动刷新，避免长期暴露风险。'},
  {icon: DashboardIcon, title: '操作审计', desc: '连接日志与云端加密录屏完整留档，行为可追溯、可回放。'},
];

// 版本对比
const plans = [
  {
    name: '个人版',
    price: '免费',
    recommended: false,
    action: '立即下载',
    items: ['远程控制与文件传输', '最高 2K 画质', '最多 10 台设备', '社区支持']
  },
  {
    name: '专业版',
    price: '¥99 / 年',
    recommended: true,
    action: '立即升级',
    items: ['4K 原画 + 60 帧高刷', '专属高速通道', '无限设备管理', '远程打印与隐私屏']
  },
  {
    name: '企业版',
    price: '按需报价',
    recommended: false,
    action: '联系销售',
    items: ['批量部署与 AD 域对接', '成员权限精细管控', '操作审计与云端录屏', '专属客户经理']
  },
];

// 常见问题
const faqs = [
  {
    q: 'WeDesk 个人版真的免费吗？',
    a: '个人版永久免费，包含远程控制、文件传输与基础画质，无需绑定支付方式即可使用；画质、通道与设备数量升级需订阅专业版。'
  },
  {
    q: '连接需要对方电脑有人操作吗？',
    a: '不需要。将设备绑定到账号后即可无人值守访问；若设备关机，配合网卡的远程唤醒（WOL）可先开机再连接。'
  },
  {
    q: '在内网或弱网环境下能连上吗？',
    a: '可以。WeLink 传输引擎会智能选路并绕开拥堵链路，30% 以内丢包基本无感；完全隔离的内网环境可选用企业版私有化部署。'
  },
  {
    q: '数据传输安全如何保障？',
    a: '连接采用端到端加密，密钥不落服务端；同时提供新设备验证、一次性临时密码、连接悬浮提醒与云端加密录屏等能力。'
  },
  {
    q: '支持哪些系统与外设？',
    a: '支持 Windows、macOS、Linux、Android、iOS / iPadOS 以及浏览器网页版；键鼠、数位板、手柄、U 盘、摄像头、打印机均可映射使用。'
  },
];

// 下载
function onDownload() {
  MessagePlugin.success('下载功能开发中，敬请期待');
}

// 联系我们
function onContact() {
  window.location.href = 'mailto:contact@alsoapp.com?subject=WeDesk 咨询';
}
</script>
