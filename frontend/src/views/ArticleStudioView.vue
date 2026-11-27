<script setup lang="ts">
/**
 * AI 文章工作台：热点话题 -> 选择生成 -> 预览 -> 复制/发布。
 *
 * 三步式引导（Step 1 选题 / Step 2 生成 / Step 3 预览），全部数据来自后端
 * /v1/articles/* 流水线；预览排版本身由 ArticlePreview.vue 承担（用户已实现）。
 *
 * 关键点：
 *  1. 平台字段映射：后端 multi_platform 用 official(公众号)，预览组件用 wechat；
 *  2. 生成是异步任务：POST 后立即轮询 GET /v1/articles/tasks/{id}，
 *     2s 一次、done/failed 终止、组件卸载清除定时器；
 *  3. 409 EVENT_GENERATING：后端全局同一时刻只跑一个生成，友好提示并允许切到该任务；
 *  4. 「发布」= 自动复制当前平台排版 HTML + 打开对应自媒体后台，粘贴即可发布；
 *  5. 支持 ?uuid=xxx 直达已有文章预览（兼容旧 /article/preview/ 链接）；
 *  6. 任务中心（抽屉）：查后端任务表展示全部生成任务的状态与当前步骤，
 *     刷新页面 / 换设备都能找回进行中的任务并跳回对应界面。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { MessagePlugin } from 'tdesign-vue-next'
import MarkdownIt from 'markdown-it'
import {
  RefreshIcon, ChevronRightIcon, CheckCircleIcon, TimeIcon,
  LinkIcon, CopyIcon, SendIcon, FileIcon,
} from 'tdesign-icons-vue-next'
import PortalHeader from '@/components/PortalHeader.vue'
import CopyRight from '@/components/CopyRight.vue'
import ArticlePreview from '@/views/ArticlePreview.vue'
import {
  getArticle, getTask, generateArticle, listTasks, listTopics, reviewTask, retryTask,
  PortalApiError,
  type ArticleDetail, type ArticleTopic, type GenerationTask, type ReviewDecision,
} from '@/services/portal/articleApi.ts'
import { cloudConfig } from '@/config.ts'

defineOptions({ name: 'ArticleStudioView' })

const route = useRoute()
const router = useRouter()

type Platform = 'wechat' | 'baijia' | 'toutiao'

/** 平台 -> 后端 multi_platform 字段映射（公众号 official -> wechat） */
const PLATFORM_FIELD: Readonly<Record<Platform, string>> = {
  wechat: 'official',
  baijia: 'baijia',
  toutiao: 'toutiao',
}

/** 平台发布后台（复制排版 HTML 后打开，粘贴即可发布） */
const PLATFORM_PUBLISH_URL: Readonly<Record<Platform, string>> = {
  wechat: 'https://mp.weixin.qq.com/',
  baijia: 'https://baijiahao.baidu.com/',
  toutiao: 'https://mp.toutiao.com/',
}
const PLATFORM_LABEL: Readonly<Record<Platform, string>> = {
  wechat: '公众号',
  baijia: '百家号',
  toutiao: '今日头条',
}

/* ==================== 状态 ==================== */
const step = ref<1 | 2 | 3>(1)
const topics = ref<ArticleTopic[]>([])
const topicsLoading = ref(false)
const topicsError = ref('')
/** 多选话题：一次批量生成多个任务，上限可配置 */
const selectedIds = ref<number[]>([])
const MAX_BATCH_TOPICS = 5
/** 是否人工审核（大纲/终审）：随生成请求提交后端，也可用服务端配置兜底 */
const needReview = ref(true)

/** 工作台正在跟进的任务（单个或批量），状态全部来自后端任务表轮询 */
const activeTasks = ref<GenerationTask[]>([])
const generating = ref(false)
const genError = ref('')
let pollTimer: ReturnType<typeof setInterval> | null = null

// HITL 审批状态：按任务隔离，批量多张审批卡互不干扰
const reviewModeByTask = ref<Record<string, 'pick' | 'modify'>>({})
const reviewSuggestByTask = ref<Record<string, string>>({})
const reviewSubmittingByTask = ref<Record<string, boolean>>({})
const reviewErrorByTask = ref<Record<string, string>>({})

const waitingTasks = computed<GenerationTask[]>(
  () => activeTasks.value.filter((t) => t.status === 'waiting_approval'),
)
const runningCount = computed<number>(
  () => activeTasks.value.filter(
    (t) => t.status === 'queued' || t.status === 'running',
  ).length,
)

/** 批量进度摘要：共 N 个：x 个执行中，y 个待审核，z 个已完成，w 个失败 */
const batchSummary = computed<string>(() => {
  const total = activeTasks.value.length
  if (!total) return ''
  const done = activeTasks.value.filter((t) => t.status === 'done').length
  const failed = activeTasks.value.filter((t) => t.status === 'failed').length
  const parts: string[] = []
  if (runningCount.value) parts.push(`${runningCount.value} 个执行中`)
  if (waitingTasks.value.length) parts.push(`${waitingTasks.value.length} 个待审核`)
  if (done) parts.push(`${done} 个已完成`)
  if (failed) parts.push(`${failed} 个失败`)
  return `共 ${total} 个任务：${parts.join('，') || '等待开始'}`
})

const selectedCount = computed<number>(() => selectedIds.value.length)

/* ==================== 审批卡 Markdown 渲染 ==================== */
/** 待审内容（大纲/终审）是 Markdown：渲染成 HTML 展示，标题/列表/表格更易读。
 *  html:false 禁止原生 HTML 直出（LLM 输出不可信，防注入）。 */
const reviewMd = new MarkdownIt({ html: false, breaks: true, linkify: true })

function reviewHtml(t: GenerationTask): string {
  return reviewMd.render(t.review_content || '')
}

const article = ref<ArticleDetail | null>(null)
const articleLoading = ref(false)
const articleError = ref('')
const activePlatform = ref<Platform>('wechat')

/* ==================== 派生数据 ==================== */
/** 正文 Markdown 图片地址解析：/images/... 是后端静态目录的站点根路径；
 *  跨源部署（VITE_API_BASE_URL 指向独立 API 域名）时补 API 根前缀，
 *  同源部署（后端托管 dist / vite 代理）保持原样。 */
function resolveImageUrls(md: string): string {
  const base = cloudConfig().apiBase
  if (!base) return md
  return md.replace(/\]\(\/images\//g, `](${base}/images/`)
}

/** 当前平台的 Markdown 正文（缺字段时给出明确占位，不显示 undefined）；
 *  素材有图时后端已选出封面（cover_image）并注入正文配图，
 *  预览把封面图置于正文最前。 */
const mdContent = computed<string>(() => {
  if (!article.value) return ''
  const field = PLATFORM_FIELD[activePlatform.value]
  const value = article.value.multi_platform?.[field]
  const body = (typeof value === 'string' && value.trim())
    ? value
    // 兜底：多平台改编缺失时用定稿正文，保证预览有内容
    : (article.value.final_article || article.value.draft || '')
  const cover = (article.value.cover_image || '').trim()
  const md = cover && !body.includes(cover)
    ? `![封面](${cover})\n\n${body}`
    : body
  return resolveImageUrls(md)
})

const articleTitle = computed<string>(() => {
  if (!article.value) return ''
  const titles = article.value.multi_platform?.title_list
  if (Array.isArray(titles) && titles.length) return String(titles[0])
  return article.value.event_title || ''
})

/** 备选标题（去掉已用于标题的第一个） */
const alternateTitles = computed<string[]>(() => {
  const titles = article.value?.multi_platform?.title_list
  if (!Array.isArray(titles)) return []
  return titles.slice(1).map((t) => String(t))
})

/* ==================== 任务中心 ==================== */
/**
 * 任务状态全部落在后端任务表（article_generation_task），前端「任务中心」
 * 直接查表展示：页面刷新、换设备、服务重启都能找回任务，并看到执行到哪一步。
 */
const taskCenterVisible = ref(false)
const taskList = ref<GenerationTask[]>([])
const taskListLoading = ref(false)
let taskListTimer: ReturnType<typeof setInterval> | null = null

const IN_PROGRESS_STATUSES: ReadonlyArray<GenerationTask['status']> = [
  'queued', 'running', 'waiting_approval',
]

const inProgressTasks = computed<GenerationTask[]>(() =>
  taskList.value.filter((t) => IN_PROGRESS_STATUSES.includes(t.status)),
)
const inProgressCount = computed<number>(() => inProgressTasks.value.length)

/** 工作流节点名 / 步骤代号 -> 用户能看懂的当前步骤文案 */
const STEP_TEXT: Readonly<Record<string, string>> = {
  queued: '排队等待',
  running: '正在执行',
  generate_outline: '生成大纲中',
  human_review_outline: '等待大纲审核',
  re_generate_outline: '按意见重写大纲中',
  generate_draft: '撰写母稿中',
  generate_multi_platform: '改编多平台版本中',
  auto_check: '自动质量检查中',
  human_final_review: '等待终审',
  outline: '等待大纲审核',
  final: '等待终审',
  done: '已完成',
  failed: '失败',
}

function stepText(t: GenerationTask): string {
  return STEP_TEXT[t.current_step] ?? (t.current_step || '—')
}

function statusLabel(status: GenerationTask['status']): string {
  switch (status) {
    case 'queued': return '排队中'
    case 'running': return '生成中'
    case 'waiting_approval': return '待人工审核'
    case 'done': return '已完成'
    case 'failed': return '失败'
  }
}

function statusTheme(status: GenerationTask['status']):
  'default' | 'primary' | 'success' | 'warning' | 'danger' {
  switch (status) {
    case 'done': return 'success'
    case 'failed': return 'danger'
    case 'waiting_approval': return 'warning'
    default: return 'primary'
  }
}

function taskAction(t: GenerationTask): string {
  if (t.status === 'done') return '查看文章'
  if (t.status === 'waiting_approval') return '去审核'
  if (t.status === 'queued' || t.status === 'running') return '查看进度'
  return ''
}

/** 拉取最近任务（任务中心与选题页提醒共用）。偶发失败不打断页面。 */
async function refreshTaskList(): Promise<void> {
  if (!taskList.value.length) taskListLoading.value = true
  try {
    const res = await listTasks(50)
    taskList.value = res.items
  } catch {
    // 列表刷新失败保持旧数据，不弹错打扰用户
  } finally {
    taskListLoading.value = false
  }
}

function stopListRefresh(): void {
  if (taskListTimer) {
    clearInterval(taskListTimer)
    taskListTimer = null
  }
}

/** 抽屉打开期间 3s 轮询列表：进行中任务的步骤变化能实时反映 */
function startListRefresh(): void {
  stopListRefresh()
  taskListTimer = setInterval(() => { void refreshTaskList() }, 3000)
}

watch(taskCenterVisible, (visible) => {
  if (visible) {
    void refreshTaskList()
    startListRefresh()
  } else {
    stopListRefresh()
  }
})

/** 从任务中心打开一个任务：done 看文章、进行中回到进度/审批卡、失败只展示错误 */
async function openTask(t: GenerationTask): Promise<void> {
  if (t.status === 'failed') return
  taskCenterVisible.value = false
  if (t.status === 'done' && t.article_uuid) {
    clearPolling()
    generating.value = false
    genError.value = ''
    articleError.value = ''
    step.value = 3
    await loadArticle(t.article_uuid)
    return
  }
  // queued / running / waiting_approval：查表恢复到对应界面
  await resumeFromTask(t.task_id)
}

/* ==================== 话题加载 ==================== */
/** 视图形态：卡片（默认）/ 列表；按采集源筛选（hot_source） */
const topicViewMode = ref<'card' | 'list'>('card')
const sourceFilter = ref('')

const allSources = computed<string[]>(() => {
  const set = new Set<string>()
  for (const t of topics.value) {
    for (const s of t.sources || []) set.add(s)
  }
  return [...set].sort((a, b) => a.localeCompare(b, 'zh'))
})

const sourceOptions = computed(() => [
  { label: '全部来源', value: '' },
  ...allSources.value.map((s) => ({ label: s, value: s })),
])

const filteredTopics = computed<ArticleTopic[]>(() => {
  if (!sourceFilter.value) return topics.value
  return topics.value.filter((t) => (t.sources || []).includes(sourceFilter.value))
})

async function loadTopics(): Promise<void> {
  topicsLoading.value = true
  topicsError.value = ''
  try {
    const res = await listTopics(100)
    topics.value = res.items
    if (!res.items.length) {
      topicsError.value = '暂无可生成的话题，请等待后台采集聚合，或联系管理员手动触发。'
    }
  } catch (e) {
    topicsError.value = e instanceof PortalApiError ? e.message : '话题加载失败，请稍后重试'
  } finally {
    topicsLoading.value = false
  }
}

/* ==================== 多选话题 ==================== */
/** 点卡片切换选中：已选则取消；超过上限给出明确提示 */
function toggleTopic(eventId: number): void {
  const idx = selectedIds.value.indexOf(eventId)
  if (idx >= 0) {
    selectedIds.value.splice(idx, 1)
    return
  }
  if (selectedIds.value.length >= MAX_BATCH_TOPICS) {
    void MessagePlugin.warning(`一次最多选择 ${MAX_BATCH_TOPICS} 个话题`)
    return
  }
  selectedIds.value.push(eventId)
}

/* ==================== 批量生成与轮询 ==================== */
function clearPolling(): void {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

/** 用最新任务记录就地更新列表（保持原有顺序） */
function upsertTask(latest: GenerationTask): void {
  const idx = activeTasks.value.findIndex((t) => t.task_id === latest.task_id)
  if (idx >= 0) activeTasks.value.splice(idx, 1, latest)
  else activeTasks.value.push(latest)
}

function taskStepPercent(t: GenerationTask): number {
  switch (t.status) {
    case 'queued': return 10
    case 'running': return 55
    case 'waiting_approval': return 70
    default: return 100
  }
}

// 状态迁移只提醒一次：轮询每 2.5s 拉一次，按 task_id 去重
const notifiedReview = new Set<string>()
const notifiedDone = new Set<string>()
const notifiedFailed = new Set<string>()

function resetNotified(): void {
  notifiedReview.clear()
  notifiedDone.clear()
  notifiedFailed.clear()
}

/** 状态变化时的用户提示：待审/完成/失败各弹一次 toast */
function notifyTransitions(tasks: GenerationTask[]): void {
  for (const t of tasks) {
    if (t.status === 'waiting_approval' && !notifiedReview.has(t.task_id)) {
      notifiedReview.add(t.task_id)
      void MessagePlugin.info(`《${t.event_title || '未命名'}》${t.review_title || '需要审核'}`)
    } else if (t.status === 'done' && !notifiedDone.has(t.task_id)) {
      notifiedDone.add(t.task_id)
      void MessagePlugin.success(`《${t.event_title || '未命名'}》文章已生成`)
    } else if (t.status === 'failed' && !notifiedFailed.has(t.task_id)) {
      notifiedFailed.add(t.task_id)
      void MessagePlugin.error(`《${t.event_title || '未命名'}》生成失败`)
    }
  }
}

/** 只轮询 queued/running；waiting_approval 停住等人，不轮询 */
function startPolling(): void {
  clearPolling()
  pollTimer = setInterval(() => { void pollActiveTasks() }, 2500)
}

async function pollActiveTasks(): Promise<void> {
  const polling = activeTasks.value.filter(
    (t) => t.status === 'queued' || t.status === 'running',
  )
  if (!polling.length) return
  try {
    const latestList = await Promise.all(polling.map((t) => getTask(t.task_id)))
    for (const latest of latestList) upsertTask(latest)
    notifyTransitions(activeTasks.value)
    // 全部进入终态/待审：停止轮询并刷新任务中心数据
    if (runningCount.value === 0) {
      clearPolling()
      generating.value = false
      void refreshTaskList()
    }
  } catch (e) {
    // 轮询偶发网络错误不打断流程，下一次继续
    genError.value = e instanceof PortalApiError ? e.message : '任务状态刷新失败，将自动重试'
  }
}

/** 点击审核按钮：modify 先展开输入框，其余直接提交。 */
function onReviewOption(t: GenerationTask, decision: ReviewDecision): void {
  if (decision === 'modify') {
    reviewModeByTask.value[t.task_id] = 'modify'
    reviewErrorByTask.value[t.task_id] = ''
    return
  }
  void handleReview(t, decision)
}

/** HITL：提交审核决定，从断点恢复该任务的工作流。 */
async function handleReview(t: GenerationTask, decision: ReviewDecision): Promise<void> {
  if (reviewSubmittingByTask.value[t.task_id]) return
  const suggest = (reviewSuggestByTask.value[t.task_id] ?? '').trim()
  if (decision === 'modify' && !suggest) {
    reviewErrorByTask.value[t.task_id] = '请填写修改意见后再提交'
    return
  }
  reviewSubmittingByTask.value[t.task_id] = true
  reviewErrorByTask.value[t.task_id] = ''
  try {
    const latest = await reviewTask(t.task_id, decision, suggest)
    upsertTask(latest)
    reviewModeByTask.value[t.task_id] = 'pick'
    reviewSuggestByTask.value[t.task_id] = ''
    if (latest.status === 'running' || latest.status === 'queued') {
      startPolling()
    }
    void refreshTaskList()
  } catch (e) {
    reviewErrorByTask.value[t.task_id] =
      e instanceof PortalApiError ? e.message : '提交审核失败，请重试'
  } finally {
    reviewSubmittingByTask.value[t.task_id] = false
  }
}

/** 取消某张审批卡的修改模式，回到决定选择 */
function cancelModify(t: GenerationTask): void {
  reviewModeByTask.value[t.task_id] = 'pick'
  reviewSuggestByTask.value[t.task_id] = ''
  reviewErrorByTask.value[t.task_id] = ''
}

/** 失败任务重试：后端有检查点则从报错节点续跑，否则从头跑首段 */
async function handleRetry(t: GenerationTask): Promise<void> {
  try {
    const latest = await retryTask(t.task_id)
    upsertTask(latest)
    notifiedFailed.delete(t.task_id)   // 重试后再次失败允许再次提醒
    await MessagePlugin.success('任务已重新提交，从上次中断处继续')
    if (step.value === 1) step.value = 2   // 从任务中心重试时进入进度页
    startPolling()
    void refreshTaskList()
  } catch (e) {
    await MessagePlugin.error(
      e instanceof PortalApiError ? e.message : '重试失败，请稍后再试',
    )
  }
}

/** 单个话题触发失败的统一文案（批量时逐话题收集） */
function describeGenerateError(e: unknown): string {
  if (e instanceof PortalApiError) {
    if (e.code === 'EVENT_GENERATING') return '该话题已有任务进行中，已跳过'
    if (e.status === 401) return '登录状态已失效，请先登录'
    if (e.code === 'GENERATOR_UNAVAILABLE') {
      return `生成服务未就绪：${e.message}（请联系管理员配置 LLM 密钥）`
    }
    if (e.code === 'EVENT_NOT_FOUND') return '话题已被清理或不存在'
    if (e.code === 'NETWORK_ERROR') return '网络连接失败'
    return e.message
  }
  return '触发生成失败'
}

/**
 * 批量生成：为每个选中话题插入一个任务（逐个 POST，单个失败不影响其它），
 * 随后进入 Step 2 统一轮询展示每个任务的进度与审批卡。
 */
async function handleGenerate(): Promise<void> {
  if (!selectedIds.value.length) {
    await MessagePlugin.warning('请先选择热点话题（最多 5 个）')
    return
  }
  generating.value = true
  genError.value = ''
  articleError.value = ''
  activeTasks.value = []
  resetNotified()

  const created: GenerationTask[] = []
  const errors: string[] = []
  for (const id of selectedIds.value) {
    const topic = topics.value.find((t) => t.event_id === id)
    const title = topic?.event_title ?? `事件 #${id}`
    try {
      created.push(await generateArticle(id, needReview.value))
    } catch (e) {
      errors.push(`${title}：${describeGenerateError(e)}`)
    }
  }

  genError.value = errors.join('；')
  if (!created.length) {
    generating.value = false
    genError.value = genError.value || '触发生成失败'
    // 全部失败必须可见：toast + 选题页内联，避免「点了没反应」
    await MessagePlugin.error(genError.value)
    return
  }

  activeTasks.value = created
  step.value = 2
  notifyTransitions(created)
  // 任务 id 写入 URL：刷新/重开页面可查表恢复；批量用 tasks= 多 id
  const query = created.length === 1
    ? { task: created[0].task_id }
    : { tasks: created.map((t) => t.task_id).join(',') }
  router.replace({ name: 'article_studio', query })
  startPolling()
  void refreshTaskList()
}

function handleStopPolling(): void {
  clearPolling()
  generating.value = false
  reviewSuggestByTask.value = {}
  reviewErrorByTask.value = {}
  step.value = 1
}

/** 批量中某个任务已完成：从 Step 2 直接进入它的文章预览 */
async function viewTaskArticle(t: GenerationTask): Promise<void> {
  clearPolling()
  generating.value = false
  step.value = 3
  if (t.article_uuid) {
    await loadArticle(t.article_uuid)
  } else {
    articleError.value = '任务已完成但未返回文章标识，请稍后从任务中心重试。'
  }
}

/* ==================== 文章详情 ==================== */
async function loadArticle(uuid: string): Promise<void> {
  articleLoading.value = true
  articleError.value = ''
  try {
    article.value = await getArticle(uuid)
    // URL 同步：便于把当前文章链接分享给他人直接预览
    router.replace({ name: 'article_preview', query: { uuid } })
  } catch (e) {
    articleError.value = e instanceof PortalApiError ? e.message : '文章详情加载失败'
  } finally {
    articleLoading.value = false
  }
}

/** 预览组件平台切换：仅切换视图，正文已随详情一次取回 */
function handlePlatformChange(platform: Platform): void {
  activePlatform.value = platform
}

/* ==================== 复制与发布 ==================== */
/**
 * 复制当前平台正文：预览组件内部的复制按钮读取的是它自己的 renderedHtml，
 * 这里复用同一套逻辑不便（DOM 在子组件内），因此发布时直接让其复制按钮获得焦点不可行。
 * 采用方案：把当前平台排版 Markdown 转为纯文本 HTML 写入剪贴板作为兜底，
 * 同时打开后台；用户也可用组件内「复制排版HTML」按钮获得带样式的完整 HTML。
 */
async function copyPlainText(): Promise<boolean> {
  const text = mdContent.value
  if (!text) return false
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    let ok = false
    try { ok = document.execCommand('copy') } catch { ok = false }
    document.body.removeChild(textarea)
    return ok
  }
}

async function handlePublish(): Promise<void> {
  if (!article.value) return
  const ok = await copyPlainText()
  if (ok) {
    await MessagePlugin.success(
      `已复制「${PLATFORM_LABEL[activePlatform.value]}」正文，请在打开的后台粘贴发布`,
    )
  } else {
    await MessagePlugin.warning('复制失败，请手动选择预览内容复制')
  }
  window.open(PLATFORM_PUBLISH_URL[activePlatform.value], '_blank', 'noopener,noreferrer')
}

function copyTitle(text: string): void {
  if (!navigator.clipboard?.writeText) return
  void navigator.clipboard.writeText(text).then(
    () => void MessagePlugin.success('标题已复制'),
    () => void MessagePlugin.error('复制失败'),
  )
}

async function handleCopyLink(): Promise<void> {
  const url = window.location.href
  try {
    await navigator.clipboard.writeText(url)
    await MessagePlugin.success('文章预览链接已复制')
  } catch {
    await MessagePlugin.error('复制失败，请手动复制地址栏链接')
  }
}

function startNew(): void {
  clearPolling()
  generating.value = false
  reviewSuggestByTask.value = {}
  reviewErrorByTask.value = {}
  activeTasks.value = []
  selectedIds.value = []
  article.value = null
  genError.value = ''
  step.value = 1
  router.replace({ name: 'article_studio' })
  void loadTopics()
  void refreshTaskList()
}

/** 时间显示：兼容两种历史格式。
 *  - 新数据：ISO 8601 带时区偏移（+00:00），浏览器直接换算本地时间；
 *  - 旧数据：无时区标记的 UTC 字符串，new Date() 会误当本地时间（显示早 8 小时），
 *    这里补 Z 强制按 UTC 解析后再转本地显示。 */
function formatTime(iso: string): string {
  if (!iso) return ''
  const hasTz = /[Zz]$|[+-]\d{2}:?\d{2}$/.test(iso)
  const normalized = hasTz ? iso : `${iso.replace(' ', 'T')}Z`
  const d = new Date(normalized)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

function formatScore(n: number): string {
  return n >= 10000 ? `${(n / 10000).toFixed(1)}万` : String(n)
}

/* ==================== 生命周期 ==================== */
/**
 * 按 task_id 查表恢复任务进度（后端状态在 article_generation_task 表，
 * 进程重启也不丢）。任务中心「去审核/查看进度」与 URL ?task= 恢复都走这里。
 *
 * 【重大 bug 修复】恢复 waiting_approval / running 任务时必须把 step 切到 2：
 * 旧实现只在 done 时跳转，待审任务恢复后 step 仍是 1，用户点「去审核」
 * 却回到选题页，审批卡根本看不到。
 */
async function resumeFromTask(taskId: string): Promise<void> {
  generating.value = false
  genError.value = ''
  articleError.value = ''
  try {
    const latest = await getTask(taskId)
    // 先载入话题，保证界面能显示所选话题标题
    await loadTopics()
    selectedIds.value = [latest.event_id]
    activeTasks.value = [latest]
    // 无论待审还是执行中，都进 Step 2（进度列表 + 审批卡）
    step.value = 2
    notifyTransitions([latest])
    if (latest.status === 'queued' || latest.status === 'running') {
      startPolling()
    }
  } catch (e) {
    // 任务已过期/被清理：回退到选题页，不让用户卡在空白状态
    genError.value = e instanceof PortalApiError
      ? `任务恢复失败：${e.message}` : '任务恢复失败，请重新选择话题生成'
    step.value = 1
    await loadTopics()
    await router.replace({ name: 'article_studio' })
  }
}

/** 批量恢复：URL ?tasks=a,b,c 时逐个查表，成功多少恢复多少 */
async function resumeFromTasks(taskIds: string[]): Promise<void> {
  generating.value = false
  genError.value = ''
  articleError.value = ''
  const results = await Promise.allSettled(taskIds.map((id) => getTask(id)))
  const tasks: GenerationTask[] = []
  for (const r of results) {
    if (r.status === 'fulfilled') tasks.push(r.value)
  }
  if (!tasks.length) {
    genError.value = '任务恢复失败：任务不存在或已被清理，请从任务中心查看历史'
    await loadTopics()
    return
  }
  await loadTopics()
  selectedIds.value = [...new Set(tasks.map((t) => t.event_id))]
  activeTasks.value = tasks
  step.value = 2
  notifyTransitions(tasks)
  if (runningCount.value > 0) startPolling()
}

onMounted(async () => {
  const uuid = route.query.uuid
  const taskId = route.query.task
  const tasksParam = route.query.tasks
  if (typeof uuid === 'string' && uuid) {
    step.value = 3
    await loadArticle(uuid)
    void refreshTaskList()
  } else if (typeof taskId === 'string' && taskId) {
    await resumeFromTask(taskId)
  } else if (typeof tasksParam === 'string' && tasksParam) {
    await resumeFromTasks(tasksParam.split(',').filter(Boolean))
  } else {
    await loadTopics()
    // 选题页同时拉一次任务表：有进行中任务时提醒用户去任务中心找回
    void refreshTaskList()
  }
})

onUnmounted(() => {
  clearPolling()
  stopListRefresh()
})
</script>

<template>
  <PortalHeader />

  <main class="mx-auto max-w-7xl px-4 pb-16">
    <!-- 页头 -->
    <div class="flex items-center justify-between flex-wrap gap-3 mb-5 mt-5">
      <div>
        <h1 class="text-[24px] font-bold">AI 文章工作台</h1>
        <p class="text-[13px] text-ink-3 mt-1">选择热点话题，一键生成多平台文章，预览后复制发布</p>
      </div>
      <div class="flex items-center gap-3">
        <t-badge :count="inProgressCount" :offset="[4, -2]">
          <t-button variant="outline" @click="taskCenterVisible = true">
            <template #icon><TimeIcon /></template>
            任务中心
          </t-button>
        </t-badge>
        <t-button variant="outline" :disabled="step === 1 && !article" @click="startNew">
          <template #icon><RefreshIcon /></template>
          新建文章
        </t-button>
      </div>
    </div>

    <!-- 步骤条 -->
    <t-steps :current="step - 1" class="mb-6" readonly>
      <t-step-item title="选择话题" />
      <t-step-item title="生成文章" />
      <t-step-item title="预览发布" />
    </t-steps>

    <!-- ========== Step 1: 选题 ========== -->
    <section v-if="step === 1">
      <!-- 进行中任务提醒：任务在数据库里，刷新/离开页面都不会丢，这里帮用户找回 -->
      <div v-if="inProgressTasks.length" class="task-banner">
        <span class="task-banner__text">
          你还有 <b>{{ inProgressTasks.length }}</b> 个生成任务未完成
          <template v-if="inProgressTasks[0]">
            （最近：{{ inProgressTasks[0].event_title || `事件 #${inProgressTasks[0].event_id}` }} · {{ stepText(inProgressTasks[0]) }}）
          </template>
        </span>
        <t-button size="small" theme="primary" variant="outline" @click="taskCenterVisible = true">
          打开任务中心
        </t-button>
      </div>

      <div class="flex items-center justify-between flex-wrap gap-2 mb-3">
        <h2 class="text-[16px] font-semibold">热点话题</h2>
        <div class="flex items-center gap-2">
          <t-select
            v-model="sourceFilter"
            :options="sourceOptions"
            placeholder="按采集源筛选"
            size="small"
            class="w-44"
            clearable
          />
          <t-radio-group v-model="topicViewMode" variant="default-filled" size="small">
            <t-radio-button value="card">卡片</t-radio-button>
            <t-radio-button value="list">列表</t-radio-button>
          </t-radio-group>
          <t-button size="small" variant="text" :loading="topicsLoading" @click="loadTopics">
            <template #icon><RefreshIcon /></template>
            刷新
          </t-button>
        </div>
      </div>

      <t-alert v-if="topicsError" theme="info" class="mb-4">
        <template #message>{{ topicsError }}</template>
      </t-alert>

      <t-loading v-if="topicsLoading" size="small" />

      <!-- 列表视图：一行一个话题，信息密度更高 -->
      <div v-else-if="topicViewMode === 'list'" class="topic-list">
        <button
          v-for="topic in filteredTopics"
          :key="topic.event_id"
          type="button"
          class="topic-row"
          :class="{
            'topic-row--selected': selectedIds.includes(topic.event_id),
            'topic-row--busy': topic.generating,
          }"
          :disabled="topic.generating"
          @click="toggleTopic(topic.event_id)"
        >
          <CheckCircleIcon
            v-if="selectedIds.includes(topic.event_id)"
            class="topic-row__check"
          />
          <span v-else class="topic-row__circle"></span>
          <div class="topic-row__main">
            <h3 class="topic-row__title">{{ topic.event_title }}</h3>
            <p v-if="topic.event_summary" class="topic-row__summary">{{ topic.event_summary }}</p>
          </div>
          <div class="topic-row__side">
            <div v-if="topic.sources?.length" class="topic-row__sources">
              <span v-for="s in topic.sources" :key="s" class="topic-card__source">{{ s }}</span>
            </div>
            <span class="topic-row__heat">🔥 {{ formatScore(topic.total_score) }}</span>
            <span v-if="topic.generating" class="topic-card__tag topic-card__tag--busy">生成中</span>
            <span v-else class="topic-card__tag">素材 {{ topic.source_urls.length }} 篇</span>
          </div>
        </button>
        <t-alert
          v-if="!filteredTopics.length"
          theme="info"
        >
          <template #message>{{ sourceFilter ? '没有匹配该采集源的话题' : '暂无话题' }}</template>
        </t-alert>
      </div>

      <div v-else class="topic-grid">
        <button
          v-for="topic in filteredTopics"
          :key="topic.event_id"
          type="button"
          class="topic-card"
          :class="{
            'topic-card--selected': selectedIds.includes(topic.event_id),
            'topic-card--busy': topic.generating,
          }"
          :disabled="topic.generating"
          @click="toggleTopic(topic.event_id)"
        >
          <div class="topic-card__top">
            <span class="topic-card__rank">#{{ topic.event_id }}</span>
            <span class="topic-card__heat">🔥 {{ formatScore(topic.total_score) }}</span>
          </div>
          <h3 class="topic-card__title">{{ topic.event_title }}</h3>
          <p v-if="topic.event_summary" class="topic-card__summary">{{ topic.event_summary }}</p>
          <div v-if="topic.sources?.length" class="topic-card__sources">
            <span v-for="s in topic.sources.slice(0, 3)" :key="s" class="topic-card__source">{{ s }}</span>
            <span v-if="topic.sources.length > 3" class="topic-card__source topic-card__source--more">
              +{{ topic.sources.length - 3 }}
            </span>
          </div>
          <div class="topic-card__foot">
            <span v-if="topic.generating" class="topic-card__tag topic-card__tag--busy">生成中</span>
            <span v-else class="topic-card__tag">素材 {{ topic.source_urls.length }} 篇</span>
            <CheckCircleIcon v-if="selectedIds.includes(topic.event_id)" class="topic-card__check" />
          </div>
        </button>
      </div>

      <!-- 触发生成阶段的错误（如 503 生成服务未配置）必须留在选题页可见，
           不能依赖 Step 2 的提示——失败时 step 仍是 1，用户会以为「点了没反应」。 -->
      <t-alert v-if="genError" theme="warning" class="mb-4">
        <template #message>{{ genError }}</template>
      </t-alert>

      <div class="sticky-bar">
        <div class="flex items-center flex-wrap gap-3">
          <t-checkbox v-model="needReview">生成后需要人工审核</t-checkbox>
          <span class="text-[13px] text-ink-3">
            {{
              selectedCount
                ? `已选择 ${selectedCount}/${MAX_BATCH_TOPICS} 个话题，将依次生成`
                : '请选择话题（可多选，最多 5 个）'
            }}
          </span>
        </div>
        <t-button
          theme="primary"
          :loading="generating"
          :disabled="!selectedIds.length || generating"
          @click="handleGenerate"
        >
          生成文章（{{ selectedCount }}） <ChevronRightIcon />
        </t-button>
      </div>
    </section>

    <!-- ========== Step 2: 批量生成进度 / 人工审核 ========== -->
    <section v-else-if="step === 2" class="gen-panel">
      <div class="gen-panel__icon"><TimeIcon /></div>
      <h2 class="text-[18px] font-semibold mt-3">
        {{ waitingTasks.length ? '请审核生成内容' : '正在生成文章' }}
      </h2>
      <p v-if="batchSummary" class="text-[13px] text-ink-3 mt-1">{{ batchSummary }}</p>

      <!-- 每个任务一行：状态、当前步骤、进度条、完成入口 -->
      <div class="batch-list">
        <div v-for="t in activeTasks" :key="t.task_id" class="batch-item">
          <div class="batch-item__head">
            <t-tag :theme="statusTheme(t.status)" variant="light" size="small">
              {{ statusLabel(t.status) }}
            </t-tag>
            <span class="batch-item__title">
              {{ t.event_title || `事件 #${t.event_id}` }}
            </span>
            <span class="batch-item__step">步骤：{{ stepText(t) }}</span>
          </div>
          <t-progress
            :percentage="taskStepPercent(t)"
            :status="t.status === 'failed' ? 'error' : 'active'"
          />
          <div class="batch-item__foot">
            <span v-if="t.status === 'failed' && t.error" class="batch-item__error">
              {{ t.error }}
            </span>
            <span v-else class="batch-item__spacer"></span>
            <t-button
              v-if="t.status === 'failed'"
              size="small"
              theme="primary"
              variant="outline"
              @click="handleRetry(t)"
            >
              重试
            </t-button>
            <t-button
              v-if="t.status === 'done' && t.article_uuid"
              size="small"
              variant="outline"
              @click="viewTaskArticle(t)"
            >
              查看文章
            </t-button>
          </div>
        </div>
      </div>

      <!-- HITL 审批卡：每个待审任务一张，工作流暂停在此等待决定 -->
      <div v-for="t in waitingTasks" :key="t.task_id" class="review-card">
        <div class="review-card__head">
          <span class="review-card__badge">
            {{ t.review_stage === 'final' ? '终审' : '大纲审核' }}
          </span>
          <span class="text-[12px] text-ink-3">
            《{{ t.event_title || `事件 #${t.event_id}` }}》 · {{ t.review_title }}
          </span>
        </div>
        <!-- 待审内容按 Markdown 渲染（标题/列表/表格），比纯文本 pre 易读 -->
        <div class="review-card__content review-card__content--md" v-html="reviewHtml(t)"></div>

        <t-alert v-if="reviewErrorByTask[t.task_id]" theme="warning" class="mb-3">
          <template #message>{{ reviewErrorByTask[t.task_id] }}</template>
        </t-alert>

        <!-- 修改意见：点「提修改意见」后展开，填完再确认提交 -->
        <template v-if="reviewModeByTask[t.task_id] === 'modify'">
          <t-textarea
            v-model="reviewSuggestByTask[t.task_id]"
            placeholder="请输入修改意见，例如：第二段补充数据来源、标题更口语化…"
            :autosize="{ minRows: 3, maxRows: 8 }"
            class="mb-3"
          />
          <div class="review-card__actions">
            <t-button theme="primary" :loading="reviewSubmittingByTask[t.task_id]"
              :disabled="!reviewSuggestByTask[t.task_id]?.trim()"
              @click="handleReview(t, 'modify')">提交修改意见</t-button>
            <t-button variant="outline" :disabled="reviewSubmittingByTask[t.task_id]"
              @click="cancelModify(t)">取消</t-button>
          </div>
        </template>

        <div v-else class="review-card__actions">
          <t-button
            v-for="opt in (t.review_options?.length ? t.review_options : ['pass', 'reject'])"
            :key="opt"
            :theme="opt === 'pass' ? 'primary' : opt === 'reject' ? 'danger' : 'default'"
            :variant="opt === 'pass' ? 'base' : 'outline'"
            :disabled="reviewSubmittingByTask[t.task_id]"
            @click="onReviewOption(t, opt)"
          >
            {{ opt === 'pass' ? '通过' : opt === 'modify' ? '提修改意见' : '拒绝' }}
          </t-button>
        </div>
        <p class="text-[12px] text-ink-3 mt-3">
          你的决定将提交给后端，工作流从断点继续；“提修改意见”会先重写大纲再请你复核。
        </p>
      </div>

      <t-alert v-if="genError" theme="warning" class="mt-4 max-w-xl">
        <template #message>{{ genError }}</template>
      </t-alert>

      <p v-if="runningCount" class="text-[12px] text-ink-3 mt-4">
        生成是长任务，通常需要几分钟；可以离开本页，随时从「任务中心」找回进度。
      </p>
      <t-button variant="outline" class="mt-3" @click="handleStopPolling">返回重选</t-button>
    </section>

    <!-- ========== Step 3: 预览与发布 ========== -->
    <section v-else>
      <t-loading v-if="articleLoading" size="small" />
      <t-alert v-if="articleError" theme="warning" class="mb-4">
        <template #message>{{ articleError }}</template>
      </t-alert>

      <template v-if="article">
        <!-- 文章信息 + 操作栏 -->
        <div class="preview-head">
          <div class="min-w-0">
            <h2 class="text-[18px] font-semibold truncate">{{ articleTitle || '未命名文章' }}</h2>
            <p class="text-[12px] text-ink-3 mt-1">
              生成于 {{ formatTime(article.create_time) }} · 模型 {{ article.model || '—' }}
            </p>
          </div>
          <div class="preview-actions">
            <t-button size="small" variant="outline" @click="handleCopyLink">
              <template #icon><LinkIcon /></template>
              复制链接
            </t-button>
            <t-button size="small" theme="primary" @click="handlePublish">
              <template #icon><SendIcon /></template>
              发布到{{ PLATFORM_LABEL[activePlatform] }}
            </t-button>
          </div>
        </div>

        <!-- 备选标题 -->
        <div v-if="alternateTitles.length" class="alt-titles">
          <span class="alt-titles__label">备选标题</span>
          <button v-for="(t, i) in alternateTitles" :key="i" type="button" class="alt-titles__item" @click="copyTitle(t)">
            <CopyIcon /> {{ t }}
          </button>
        </div>

        <!-- 预览组件（用户已实现的多平台排版预览） -->
        <ArticlePreview
          :platform="activePlatform"
          :md-content="mdContent"
          :title="articleTitle"
          @change="handlePlatformChange"
        />
        <p class="text-[12px] text-ink-3 mt-3 flex items-center gap-1">
          <FileIcon /> 提示：用预览组件右上角「复制排版HTML」可复制带样式的成品，粘贴到后台排版不丢失。
        </p>
      </template>
    </section>
  </main>

  <!-- ========== 任务中心抽屉：查任务表展示全部生成任务 ========== -->
  <t-drawer
    v-model:visible="taskCenterVisible"
    header="任务中心"
    :footer="false"
    size="460px"
    close-btn
  >
    <t-loading v-if="taskListLoading && !taskList.length" size="small" text="加载中..." />
    <p v-else-if="!taskList.length" class="text-[13px] text-ink-3">
      暂无任务记录，选择话题后点击「生成文章」即可开始。
    </p>
    <div v-else class="task-list">
      <button
        v-for="t in taskList"
        :key="t.task_id"
        type="button"
        class="task-item"
        :class="{ 'task-item--dead': t.status === 'failed' }"
        @click="openTask(t)"
      >
        <div class="task-item__head">
          <t-tag :theme="statusTheme(t.status)" variant="light" size="small">
            {{ statusLabel(t.status) }}
          </t-tag>
          <span class="task-item__title">{{ t.event_title || `事件 #${t.event_id}` }}</span>
          <span
            v-if="t.status === 'failed'"
            class="task-item__action"
            @click.stop="handleRetry(t)"
          >重试 ↻</span>
          <span v-else-if="taskAction(t)" class="task-item__action">{{ taskAction(t) }} →</span>
        </div>
        <div class="task-item__meta">
          <span>步骤：{{ stepText(t) }}</span>
          <span>{{ formatTime(t.created_at) }}</span>
        </div>
        <p v-if="t.status === 'failed' && t.error" class="task-item__error">{{ t.error }}</p>
      </button>
      <p class="text-[12px] text-ink-3 mt-2">
        任务记录保存在服务器，页面刷新或换设备打开都不会丢失；失败任务可一键重试，
        服务重启后未完成任务也会自动从断点续跑。
      </p>
    </div>
  </t-drawer>

  <CopyRight />
</template>

<style scoped>
.topic-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.topic-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  text-align: left;
  cursor: pointer;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  transition: border-color .2s, box-shadow .2s;
}

.topic-card:hover:not(:disabled) {
  border-color: #1a6eeb;
  box-shadow: 0 2px 10px rgb(26 110 235 / 10%);
}

.topic-card--selected {
  background: #f5f9ff;
  border-color: #1a6eeb;
}

.topic-card--busy {
  cursor: not-allowed;
  opacity: .6;
}

.topic-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: #8a9099;
}

.topic-card__heat {
  color: #e0713a;
}

.topic-card__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.5;
  color: #1f2328;
}

.topic-card__summary {
  display: -webkit-box;
  overflow: hidden;
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: #6b7280;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.topic-card__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: auto;
}

.topic-card__tag {
  padding: 2px 8px;
  font-size: 11px;
  color: #1a6eeb;
  background: #eaf2ff;
  border-radius: 10px;
}

.topic-card__tag--busy {
  color: #b26a00;
  background: #fff3e0;
}

.topic-card__check {
  color: #1a6eeb;
}

/* 采集源标签：卡片与列表共用 */
.topic-card__sources {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.topic-card__source {
  padding: 1px 8px;
  font-size: 11px;
  color: #58606a;
  background: #f1f3f5;
  border-radius: 9px;
  white-space: nowrap;
}

.topic-card__source--more {
  color: #8a9099;
}

/* 列表视图 */
.topic-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.topic-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  text-align: left;
  cursor: pointer;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  transition: border-color .2s, box-shadow .2s;
}

.topic-row:hover:not(:disabled) {
  border-color: #1a6eeb;
  box-shadow: 0 2px 10px rgb(26 110 235 / 10%);
}

.topic-row--selected {
  background: #f5f9ff;
  border-color: #1a6eeb;
}

.topic-row--busy {
  cursor: not-allowed;
  opacity: .6;
}

.topic-row__circle {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  border: 1.5px solid #c9ced6;
  border-radius: 50%;
}

.topic-row__check {
  flex-shrink: 0;
  font-size: 18px;
  color: #1a6eeb;
}

.topic-row__main {
  flex: 1;
  min-width: 0;
}

.topic-row__title {
  margin: 0;
  overflow: hidden;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.5;
  color: #1f2328;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topic-row__summary {
  display: -webkit-box;
  overflow: hidden;
  margin: 2px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: #6b7280;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
}

.topic-row__side {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 8px;
}

.topic-row__sources {
  display: flex;
  flex-wrap: wrap;
  max-width: 220px;
  gap: 4px;
}

.topic-row__heat {
  font-size: 12px;
  color: #e0713a;
}

.batch-item__spacer {
  flex: 1;
}

.sticky-bar {
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 20px;
  padding: 12px 16px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 -2px 12px rgb(0 0 0 / 5%);
}

.gen-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60px 20px;
  text-align: center;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.gen-panel__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  font-size: 28px;
  color: #1a6eeb;
  background: #eaf2ff;
  border-radius: 50%;
}

.preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.preview-actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
}

.alt-titles {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 10px 14px;
  background: #fafbfc;
  border: 1px solid #eef0f3;
  border-radius: 8px;
}

.alt-titles__label {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
}

.alt-titles__item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 12px;
  color: #1a6eeb;
  cursor: pointer;
  background: #fff;
  border: 1px solid #dbe7fa;
  border-radius: 14px;
}

.alt-titles__item:hover {
  background: #eaf2ff;
}

/* Step 2 批量任务列表 */
.batch-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
  max-width: 760px;
  margin-top: 20px;
}

.batch-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  background: #f8fafc;
  border: 1px solid #eef0f3;
  border-radius: 8px;
}

.batch-item__head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.batch-item__title {
  flex: 1;
  overflow: hidden;
  font-size: 13px;
  font-weight: 600;
  color: #1f2328;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.batch-item__step {
  flex-shrink: 0;
  font-size: 12px;
  color: #6b7280;
}

.batch-item__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 0;
}

.batch-item__error {
  overflow: hidden;
  font-size: 12px;
  line-height: 1.6;
  color: #b42318;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 进行中任务提醒条（选题页） */
.task-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
  padding: 10px 14px;
  background: #f5f9ff;
  border: 1px solid #c8dcfa;
  border-radius: 8px;
}

.task-banner__text {
  font-size: 13px;
  color: #1f2328;
}

/* 任务中心列表 */
.task-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.task-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  text-align: left;
  cursor: pointer;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  transition: border-color .2s, box-shadow .2s;
}

.task-item:hover {
  border-color: #1a6eeb;
  box-shadow: 0 2px 10px rgb(26 110 235 / 10%);
}

.task-item--dead {
  cursor: default;
}

.task-item--dead:hover {
  border-color: #e5e7eb;
  box-shadow: none;
}

.task-item__head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.task-item__title {
  flex: 1;
  overflow: hidden;
  font-size: 13px;
  font-weight: 600;
  color: #1f2328;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-item__action {
  flex-shrink: 0;
  font-size: 12px;
  color: #1a6eeb;
}

.task-item__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: #6b7280;
}

.task-item__error {
  margin: 0;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.6;
  color: #b42318;
  background: #fef3f2;
  border-radius: 6px;
  word-break: break-word;
}

/* HITL 审批卡 */
/* gen-panel 是居中布局（text-align:center + align-items:center），
   审批卡必须显式拉回左对齐并占满行宽，否则 Markdown 渲染内容整体居中且收缩，
   可读性极差（回归 bug：审批内容全部居中）。 */
.review-card {
  width: 100%;
  max-width: 760px;
  margin-top: 20px;
  padding: 18px 20px;
  text-align: left;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  box-shadow: 0 2px 14px rgb(26 110 235 / 8%);
}

.review-card__head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.review-card__badge {
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 600;
  color: #1a6eeb;
  background: #eaf2ff;
  border-radius: 12px;
}

.review-card__content {
  max-height: 420px;
  margin: 0 0 16px;
  padding: 14px 16px;
  overflow: auto;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.7;
  color: #1f2328;
  white-space: pre-wrap;
  word-break: break-word;
  background: #f8fafc;
  border: 1px solid #eef0f3;
  border-radius: 8px;
}

/* Markdown 渲染后的待审内容：恢复正常换行并给基本元素样式 */
.review-card__content--md {
  white-space: normal;
}

.review-card__content--md :deep(h1),
.review-card__content--md :deep(h2),
.review-card__content--md :deep(h3),
.review-card__content--md :deep(h4) {
  margin: 12px 0 6px;
  font-size: 14px;
  line-height: 1.5;
}

.review-card__content--md :deep(h1:first-child),
.review-card__content--md :deep(h2:first-child),
.review-card__content--md :deep(h3:first-child) {
  margin-top: 0;
}

.review-card__content--md :deep(p) {
  margin: 6px 0;
}

.review-card__content--md :deep(ul),
.review-card__content--md :deep(ol) {
  margin: 6px 0;
  padding-left: 20px;
}

.review-card__content--md :deep(li) {
  margin: 3px 0;
}

.review-card__content--md :deep(table) {
  margin: 8px 0;
  border-collapse: collapse;
  font-size: 12px;
}

.review-card__content--md :deep(th),
.review-card__content--md :deep(td) {
  padding: 4px 8px;
  border: 1px solid #d8dee6;
}

.review-card__content--md :deep(code) {
  padding: 1px 5px;
  font-size: 12px;
  background: #eceff3;
  border-radius: 4px;
}

.review-card__content--md :deep(blockquote) {
  margin: 8px 0;
  padding: 2px 12px;
  color: #6b7280;
  border-left: 3px solid #c8dcfa;
}

.review-card__content--md :deep(hr) {
  margin: 10px 0;
  border: none;
  border-top: 1px solid #d8dee6;
}

.review-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

@media (max-width: 640px) {
  .preview-head { flex-direction: column; align-items: stretch; }
  .preview-actions { justify-content: flex-end; }
  .review-card__actions { flex-direction: column; }
}
</style>
