<template>
  <PageLayout title="在吗">
    <!-- 首屏 -->
    <section
        class="mb-10 rounded-lg bg-gradient-to-br from-[#7c2d12] via-[#c2410c] to-[#f59e0b] px-6 py-12 text-white sm:px-10 sm:py-16"
    >
      <div class="grid items-center gap-8 lg:grid-cols-2">
        <div>
          <t-tag theme="warning" variant="light" class="mb-4">为牵挂而生的签到 App</t-tag>
          <h1 class="mb-3 text-4xl font-bold leading-tight sm:text-5xl">在吗</h1>
          <p class="mb-6 text-lg font-medium text-white/90 sm:text-xl">每天一句「我在」，让牵挂有回应。</p>
          <p class="mb-6 text-base leading-7 text-white/80">
            为独居老人、孩子和远方亲人设计的定时签到工具。到点温柔提醒，一键报平安；
            若超时未签到，自动通知你在意的人。
          </p>
          <div class="flex flex-wrap items-center gap-3">
            <t-button theme="primary" size="large" @click="onDownload">
              <template #icon>
                <DownloadIcon/>
              </template>
              免费下载 Android
            </t-button>
            <t-button theme="default" variant="outline" size="large" @click="onBeta">
              <template #icon>
                <RocketIcon/>
              </template>
              加入 iOS 内测
            </t-button>
          </div>
          <p class="mt-4 text-sm text-white/70">个人版永久免费 · 无需注册即可试用 · 安装包不到 15MB</p>
        </div>

        <!-- 手机示意 -->
        <div class="hidden justify-center lg:flex">
          <div class="w-64 rounded-[2rem] border-4 border-white/30 bg-white p-4 shadow-2xl">
            <div class="mb-3 text-center text-sm font-semibold text-gray-800">今天已签到</div>
            <div class="mb-4 flex justify-center">
              <div class="flex h-28 w-28 items-center justify-center rounded-full bg-orange-500 text-2xl font-bold text-white">
                我在
              </div>
            </div>
            <div class="space-y-2">
              <div class="flex items-center justify-between rounded bg-gray-100 px-3 py-2 text-xs text-gray-600">
                <span class="flex items-center gap-1">
                  <TimeIcon size="14px"/> 早间签到
                </span>
                <span class="text-green-600">已完成</span>
              </div>
              <div class="flex items-center justify-between rounded bg-gray-100 px-3 py-2 text-xs text-gray-600">
                <span class="flex items-center gap-1">
                  <AlarmIcon size="14px"/> 晚间签到
                </span>
                <span class="text-orange-500">19:30 提醒</span>
              </div>
              <div class="flex items-center justify-between rounded bg-gray-100 px-3 py-2 text-xs text-gray-600">
                <span class="flex items-center gap-1">
                  <UsergroupIcon size="14px"/> 守护人
                </span>
                <span class="text-gray-500">2 位已通知</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 关键数据 -->
      <div class="mt-10 grid grid-cols-2 gap-4 border-t border-white/20 pt-8 sm:grid-cols-4">
        <div v-for="(m, index) in metricList" :key="index">
          <div class="text-2xl font-bold sm:text-3xl">{{ m.value }}</div>
          <div class="mt-1 text-sm text-white/75">{{ m.label }}</div>
        </div>
      </div>
    </section>

    <!-- 为什么做 -->
    <section class="mb-10">
      <h2 class="mb-1 text-center text-2xl font-bold">有些担心，不该等到出事才说出口</h2>
      <p class="mb-6 text-center text-sm text-gray-500">三件小事，是「在吗」被做出来的全部理由</p>
      <div class="grid gap-4 md:grid-cols-3">
        <t-card v-for="(p, index) in pains" :key="index" :bordered="true" header-bordered>
          <template #title>
            <div class="flex items-center gap-2">
              <component :is="p.icon" size="22px" fill-color="#c2410c"/>
              <span class="font-semibold">{{ p.title }}</span>
            </div>
          </template>
          <p class="text-sm leading-6 text-gray-600">{{ p.desc }}</p>
        </t-card>
      </div>
    </section>

    <!-- 工作流程 -->
    <section class="mb-10">
      <h2 class="mb-6 text-center text-2xl font-bold">四步跑通，剩下的交给我们</h2>
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div
            v-for="(step, index) in steps"
            :key="index"
            class="relative rounded-lg border border-gray-200 p-5"
        >
          <div class="mb-3 flex h-9 w-9 items-center justify-center rounded-full bg-orange-500 text-base font-bold text-white">
            {{ index + 1 }}
          </div>
          <h3 class="mb-1 text-base font-semibold">{{ step.title }}</h3>
          <p class="text-sm leading-6 text-gray-600">{{ step.desc }}</p>
        </div>
      </div>
    </section>

    <!-- 核心功能 -->
    <section class="mb-10">
      <h2 class="mb-6 text-center text-2xl font-bold">核心功能</h2>
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <t-card v-for="(f, index) in features" :key="index" :bordered="true">
          <div class="flex items-start gap-3">
            <div class="rounded bg-orange-50 p-2">
              <component :is="f.icon" size="20px" fill-color="#c2410c"/>
            </div>
            <div>
              <h3 class="mb-1 text-base font-semibold">{{ f.title }}</h3>
              <p class="text-sm leading-6 text-gray-600">{{ f.desc }}</p>
            </div>
          </div>
        </t-card>
      </div>
    </section>

    <!-- 为谁设计 -->
    <section class="mb-10">
      <h2 class="mb-6 text-center text-2xl font-bold">为谁而设计</h2>
      <t-tabs v-model="activeScene" class="mb-4">
        <t-tab-panel v-for="(s, index) in scenes" :key="index" :value="index" :label="s.name">
          <div class="rounded-lg bg-orange-50/60 p-5">
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

    <!-- 隐私承诺 -->
    <section class="mb-10">
      <h2 class="mb-6 text-center text-2xl font-bold">隐私承诺</h2>
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div v-for="(s, index) in securities" :key="index" class="rounded-lg border border-gray-200 p-4">
          <component :is="s.icon" size="24px" fill-color="#00a870"/>
          <h3 class="mb-1 mt-2 text-base font-semibold">{{ s.title }}</h3>
          <p class="text-sm leading-6 text-gray-600">{{ s.desc }}</p>
        </div>
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
    <section class="rounded-lg bg-gradient-to-r from-[#c2410c] to-[#f59e0b] px-6 py-10 text-center text-white">
      <h2 class="mb-2 text-2xl font-bold">今晚就设好第一个签到时间</h2>
      <p class="mb-5 text-sm text-white/85">每天一句「我在」，换成一夜安稳的睡眠</p>
      <div class="flex flex-wrap justify-center gap-3">
        <t-button theme="default" size="large" @click="onDownload">
          <template #icon>
            <DownloadIcon/>
          </template>
          下载「在吗」
        </t-button>
        <t-button theme="default" variant="outline" size="large" @click="onContact">
          <template #icon>
            <MailIcon/>
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
  RocketIcon,
  MailIcon,
  TimeIcon,
  AlarmIcon,
  UsergroupIcon,
  HeartIcon,
  NotificationIcon,
  Location1Icon,
  HistoryIcon,
  User1Icon,
  FileSafetyIcon,
  FingerprintIcon,
  LockOnIcon,
  CheckCircleIcon,
} from 'tdesign-icons-vue-next';

// 当前激活的场景 Tab
const activeScene = ref(0);
// 当前展开的常见问题
const activeFaq = ref([0]);

// 关键数据
const metricList = [
  {value: '3 步', label: '完成一次签到'},
  {value: '1 键', label: '一键报平安'},
  {value: '30 秒', label: '超时通知守护人'},
  {value: '0 广告', label: '无广告无弹窗'},
];

// 为什么做
const pains = [
  {
    icon: HeartIcon,
    title: '报喜不报忧',
    desc: '父母总说"没事"，真有事的时候，你却往往是最后一个知道的。一句定时签到，把这份信息差补上。'
  },
  {
    icon: TimeIcon,
    title: '悬着的心',
    desc: '孩子说放学就回家，晚了半小时，你已经开始胡思乱想。设个签到时间，到点就有确定答案。'
  },
  {
    icon: User1Icon,
    title: '远水解不了近渴',
    desc: '异地打拼想关心却不知从何开口。「在吗」把牵挂变成一句轻松的日常问候，而不是紧急时刻的电话。'
  },
];

// 工作流程
const steps = [
  {title: '设置签到时间', desc: '早、中、晚可分别设置，支持仅工作日、周末等重复规则。'},
  {title: '到点温柔提醒', desc: '大字提醒配合轻柔铃声，长辈不需要学习也会用。'},
  {title: '一键「我在」', desc: '首页一个大按钮，一按完成签到，顺手还能写句留言。'},
  {title: '超时自动通知', desc: '超过设定时长未签到，推送 + 短信双通道告知全部守护人。'},
];

// 核心功能
const features = [
  {icon: AlarmIcon, title: '多时段定时签到', desc: '一天可设多个签到时段，支持按周重复，节假日可一键暂停。'},
  {icon: NotificationIcon, title: '超时自动告警', desc: '未按时签到自动通知守护圈所有人，短信通道确保不漏消息。'},
  {icon: HeartIcon, title: '一键报平安', desc: '首页超大按钮，一按即签到，长辈零学习成本，也能附一句留言。'},
  {icon: UsergroupIcon, title: '守护圈', desc: '多位家人共同关注同一位亲人，谁收到提醒、谁处理了都一目了然。'},
  {icon: Location1Icon, title: '位置共享（可选）', desc: '仅在授权并开启后于签到时段共享，随时可关闭，不常驻后台。'},
  {icon: HistoryIcon, title: '签到历史与周报', desc: '连续签到天数、月度出勤率一眼看清，异常时段自动标红。'},
  {icon: LockOnIcon, title: '紧急求助 SOS', desc: '长按首页按钮直接拨打紧急联系人，并同步当前位置信息。'},
  {icon: User1Icon, title: '大字极简界面', desc: '大字体、高对比度、无广告弹窗，专为长辈与孩子设计的清爽界面。'},
];

// 为谁设计
const scenes = [
  {
    name: '独居老人',
    summary: '让远方的子女每天都知道父母安好。',
    points: [
      '早间签到即报平安，晚间断签自动提醒子女',
      '大字界面 + 温柔铃声，不需要智能机使用经验',
      'SOS 长按拨号，意外时刻争取最宝贵的时间'
    ]
  },
  {
    name: '家有学龄孩子',
    summary: '放学、补习、晚归，每一步都有确定回音。',
    points: [
      '到校、到家分别设签到时间，超时即通知家长',
      '孩子一按即完成，不打断写作业',
      '守护圈里爸妈爷爷奶奶都能同步看到'
    ]
  },
  {
    name: '异地打拼的子女',
    summary: '把牵挂变成一句轻松的日常问候。',
    points: [
      '不用每天打电话追问"吃了吗"，签到即安心',
      '断签趋势异常时主动提示，防患于未然',
      '留言功能让爸妈也能给你留句语音'
    ]
  },
  {
    name: '术后康复与慢病',
    summary: '出院后的观察期，需要更密集的关注。',
    points: [
      '按医嘱设置服药、复健等多个签到时段',
      '历史记录可导出，复诊时给医生参考',
      '多位守护人分工接收，谁有空谁响应'
    ]
  },
];

// 隐私承诺
const securities = [
  {icon: FileSafetyIcon, title: '最小化收集', desc: '只收集签到时间与状态，不读取通讯录、相册等无关信息。'},
  {icon: FingerprintIcon, title: '传输与存储加密', desc: '全链路加密传输，本地数据落盘加密，守护关系需双向确认。'},
  {icon: LockOnIcon, title: '位置默认关闭', desc: '位置共享默认关闭，仅在开启后于签到时段使用，可随时撤回。'},
  {icon: User1Icon, title: '绝不出售数据', desc: '不做广告变现，不向任何第三方出售或共享个人数据。'},
];

// 常见问题
const faqs = [
  {
    q: '双方都需要安装「在吗」吗？',
    a: '被守护的老人或孩子安装主 App 完成签到；守护人安装后即可接收签到状态与超时通知，不需要额外设备。'
  },
  {
    q: '老人用的是功能机，可以用吗？',
    a: '目前需要 Android 5.0 及以上或 iOS 13 及以上。功能机短信签到已在规划中，上线后会第一时间支持。'
  },
  {
    q: '超时通知通过什么方式发送？',
    a: 'App 推送与短信双通道并行。即使守护人手机静音或断网，短信也能确保消息送达。'
  },
  {
    q: '会一直在后台定位吗？',
    a: '不会。位置共享默认关闭，仅在开启后于签到时段内获取位置，退出时段后自动停止，也不会常驻后台。'
  },
  {
    q: '收费吗？',
    a: '个人版永久免费，支持 1 位被守护人与 2 位守护人。守护人数更多或需要短信通道时，可订阅家庭版。'
  },
];

// 下载
function onDownload() {
  MessagePlugin.success('安装包准备中，留下邮箱可第一时间获得下载链接');
}

// 加入 iOS 内测
function onBeta() {
  window.location.href = 'mailto:contact@alsoapp.com?subject=在吗 iOS 内测申请';
}

// 联系我们
function onContact() {
  window.location.href = 'mailto:contact@alsoapp.com?subject=在吗 App 咨询';
}
</script>
