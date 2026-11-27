/**
 * AI 文章工作台接线静态守卫（node --test，无 DOM / 无浏览器）。
 *
 * 回归背景：`ArticlePreview.vue` 是需要 props 的纯展示组件，早期被当成路由页面
 * 直接挂载，导致 platform/mdContent/title 全为 undefined，页面永远显示空壳且复制
 * 按钮灰掉；话题列表、生成触发、任务轮询、发布入口也完全没有前端代码。这类
 * 「文件存在但没接线」的缺陷不会报错，typecheck 与纯逻辑单测都发现不了，只能用
 * 模板/源码静态断言兜住。
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(fileURLToPath(new URL('..', import.meta.url)))
const read = (rel: string): string => readFileSync(resolve(ROOT, rel), 'utf8')
/** 仓库根目录（frontend 的上一级）：用于读后端源码做前后端契约断言 */
const REPO_ROOT = resolve(ROOT, '..')
const readRepo = (rel: string): string => readFileSync(resolve(REPO_ROOT, rel), 'utf8')

const studio = read('src/views/ArticleStudioView.vue')
const preview = read('src/views/ArticlePreview.vue')
const routes = read('src/router/index.ts')
const api = read('src/services/portal/articleApi.ts')
const pkg = read('package.json')
const config = readRepo('backend/app/core/config.py')
const llmSrc = readRepo('backend/app/article/llm.py')
const routerSrc = readRepo('backend/app/article/router.py')
const modelsSrc = readRepo('backend/app/article/models.py')
const serviceSrc = readRepo('backend/app/article/service.py')

test('工作台页面真实接线预览组件（传 props 并监听平台切换）', () => {
  assert.match(studio, /<ArticlePreview\b/, '工作台未使用 ArticlePreview 组件')
  assert.match(studio, /:platform="activePlatform"/, '未传 platform prop')
  assert.match(studio, /:md-content="mdContent"/, '未传 mdContent prop')
  assert.match(studio, /:title="articleTitle"/, '未传 title prop')
  assert.match(studio, /@change="handlePlatformChange"/, '未监听平台切换，Tab 点击后正文不会变')
})

test('平台字段映射正确：公众号 official -> wechat，且三类平台齐全', () => {
  assert.match(studio, /wechat:\s*'official'/, '公众号字段映射缺失（后端叫 official）')
  assert.match(studio, /baijia:\s*'baijia'/, '百家号映射缺失')
  assert.match(studio, /toutiao:\s*'toutiao'/, '头条映射缺失')
})

test('生成链路完整：触发 + 轮询 + 任务终态处理 + 定时器清理', () => {
  assert.match(api, /\/v1\/articles\/generate/, '缺少生成接口')
  assert.match(api, /\/v1\/articles\/topics/, '缺少话题列表接口')
  assert.match(api, /\/v1\/articles\/tasks\/\$\{encodeURIComponent\(taskId\)\}/, '缺少任务查询接口')
  assert.match(studio, /setInterval/, '未轮询任务状态')
  assert.match(studio, /status === 'done'/, '未处理生成完成')
  assert.match(studio, /status === 'failed'/, '未处理生成失败')
  assert.match(studio, /clearInterval\(pollTimer\)/, '未清理定时器，卸载后会内存泄漏')
  assert.match(
    studio,
    /onUnmounted\(\(\) => \{[\s\S]{0,120}clearPolling\(\)[\s\S]{0,120}stopListRefresh\(\)/,
    '组件卸载未停止轮询/任务列表定时器',
  )
})

test('生成失败必须可见：503 等错误有 toast + 选题页内联提示 + 按钮 loading', () => {
  // 回归 bug：catch 里除 409/401 外只写 genError，且 genError 只在 Step 2 渲染，
  // 失败时 step 仍为 1 => 用户点击后完全看不到反馈，误以为「没反应」。
  assert.match(studio, /code === 'GENERATOR_UNAVAILABLE'/, '未处理 503 生成服务未就绪')
  assert.match(studio, /MessagePlugin\.error\(genError\.value\)/, '致命错误没有 toast 提示')
  assert.match(studio, /v-if="genError"[\s\S]{0,400}sticky-bar/, '选题页未内联展示触发生成错误')
  assert.match(studio, /:loading="generating"/, '生成按钮缺少 loading 态，点击后无即时反馈')
  assert.match(
    studio,
    /:disabled="!selectedIds\.length \|\| generating"/,
    '生成中未禁用按钮，可重复提交',
  )
})

test('多选话题批量生成：上限可配置 + 逐话题提交 + 批量进度', () => {
  assert.match(studio, /selectedIds/, '话题未改为多选')
  assert.match(studio, /MAX_BATCH_TOPICS = 5/, '缺少批量上限常量（可配置）')
  assert.match(studio, /toggleTopic/, '话题卡片未接线多选切换')
  assert.match(studio, /selectedIds\.value\.length >= MAX_BATCH_TOPICS/, '超过上限未拦截')
  assert.match(api, /needReview\?: boolean/, '生成接口缺少人工审核开关参数')
  assert.match(
    studio,
    /generateArticle\(id, needReview\.value\)/,
    '批量提交未透传人工审核开关',
  )
  assert.match(studio, /batchSummary/, 'Step 2 缺少批量进度摘要')
  assert.match(studio, /batch-item/, 'Step 2 缺少逐任务进度列表')
  assert.match(studio, /viewTaskArticle/, '批量中已完成任务缺少查看文章入口')
  assert.match(studio, /tasks:\s*created\.map/, '批量任务未写入 URL，刷新无法恢复')
})

test('人工审核可配置：选题页开关 + 后端配置兜底', () => {
  assert.match(studio, /t-checkbox v-model="needReview"/, '选题页缺少人工审核开关')
  // 后端：配置项 + 审核节点自动通过 + 请求参数优先
  assert.match(config, /ARTICLE_HITL_ENABLED/, '后端缺少人工审核配置项')
  assert.match(llmSrc, /need_review/, '工作流 state 缺少 need_review 字段')
  assert.match(
    llmSrc,
    /if not state\.get\("need_review", True\)/,
    '审核节点未按配置自动通过',
  )
  assert.match(routerSrc, /need_review/, '生成接口未接收 need_review 参数')
})

test('HITL 前端审批链：待审字段 + 审批卡 + 提交/修改/取消', () => {
  // 回归背景：后端把大纲/终审改为 LangGraph interrupt 暂停，前端必须能展示待审内容并提交决定。
  assert.match(api, /reviewTask/, '缺少 HITL 审批接口封装')
  assert.match(api, /\/review/, '审批接口路径缺失')
  assert.match(api, /waiting_approval/, 'GenerationTask 缺少 waiting_approval 状态')
  assert.match(api, /review_content/, 'GenerationTask 缺少待审内容字段')
  assert.match(studio, /waitingTasks/, '工作台未识别等待审核的任务')
  assert.match(studio, /review-card__content/, '审批卡未展示待审内容')
  assert.match(studio, /@click="onReviewOption\(t, opt\)"/, '审批按钮未接线')
  assert.match(studio, /handleReview\(t, 'modify'\)/, '修改意见未接线')
  assert.match(studio, /@click="cancelModify\(t\)"/, '缺少取消修改')
  // 待审任务不参与轮询（等人决定），全部离开执行态后停止轮询
  assert.match(
    studio,
    /status === 'queued' \|\| t\.status === 'running'\s*\)/,
    '轮询未限定执行中任务',
  )
  assert.match(studio, /runningCount\.value === 0/, '全部任务离开执行态后未停止轮询')
})

test('任务恢复必须进入生成界面（去审核跳回选题页的回归 bug）', () => {
  // 回归 bug：resumeFromTask 恢复 waiting_approval 任务时不设置 step，
  // 任务中心点「去审核」停在 Step 1 选题页，审批卡看不到。
  assert.match(
    studio,
    /activeTasks\.value = \[latest\][\s\S]{0,200}step\.value = 2/,
    '恢复单个任务未切到 Step 2（去审核会跳回选题页）',
  )
  assert.match(
    studio,
    /activeTasks\.value = tasks[\s\S]{0,200}step\.value = 2/,
    '批量恢复任务未切到 Step 2',
  )
  assert.match(
    studio,
    /resumeFromTasks/,
    'URL ?tasks= 批量恢复逻辑缺失',
  )
})

test('审批提交必须异步返回（同步跑下一段会撞前端 15s 超时）', () => {
  // 回归 bug：POST /review 同步等待下一段 LLM 生成（分钟级），前端 15s fetch
  // 超时被误报「网络错误」，用户以为提交失败实际工作流还在跑。
  assert.match(
    serviceSrc,
    /asyncio\.create_task\(_run_resume_segment\(\)/,
    '审批后的下一段仍在 POST 内同步执行，必然超时',
  )
})

test('审批卡 Markdown 渲染 + 时间全程带时区', () => {
  // 待审内容（大纲/终审）是 Markdown：渲染成 HTML 才易读
  assert.match(studio, /v-html="reviewHtml\(t\)"/, '审批卡未按 Markdown 渲染待审内容')
  assert.match(studio, /html: false/, 'Markdown 渲染未禁用原生 HTML（防注入）')
  // 时间：后端存储带时区，前端兼容历史无时区字符串
  assert.doesNotMatch(modelsSrc, /NaiveDatetime/, '表模型仍在用 naive datetime 注解')
  assert.match(modelsSrc, /return datetime\.now\(timezone\.utc\)/, 'utcnow 未返回带时区 UTC')
  assert.match(serviceSrc, /isoformat\(timespec="seconds"\)/, '任务时间戳未带时区偏移')
  assert.match(serviceSrc, /migrate_time_columns/, '缺少存量时间列 timestamptz 迁移')
  assert.match(studio, /replace\(' ', 'T'\)\}Z/, '前端未兼容历史无时区 UTC 字符串')
})

test('任务中心：查任务列表 + 步骤文案 + 进行中提醒 + 可跳回任务', () => {
  // 回归背景：任务状态在数据库里，但前端没有任务中心入口，页面刷新后用户找不到
  // 进行中的任务，也看不到执行到哪一步。
  assert.match(api, /\/v1\/articles\/tasks\?limit=/, '缺少任务列表接口路径')
  assert.match(api, /current_step/, 'GenerationTask 缺少 current_step 字段')
  assert.match(studio, /listTasks/, '工作台未调用任务列表接口')
  assert.match(studio, /taskCenterVisible/, '任务中心抽屉未接线')
  assert.match(studio, /t-drawer/, '任务中心未用抽屉展示')
  assert.match(studio, /STEP_TEXT/, '缺少步骤名 -> 中文文案映射，用户看不懂节点名')
  assert.match(studio, /步骤：\{\{ stepText\(t\) \}\}/, '进度页未展示当前步骤')
  assert.match(studio, /inProgressTasks/, '选题页缺少进行中任务提醒')
  assert.match(studio, /@click="openTask\(t\)"/, '任务列表项未接线点击跳转')
  assert.match(studio, /resumeFromTask\(t\.task_id\)/, '进行中任务无法跳回进度/审批界面')
  assert.match(studio, /loadArticle\(t\.article_uuid\)/, '已完成任务无法跳回文章预览')
})

test('话题列表/卡片双视图 + 按采集源筛选 + 卡片展示来源', () => {
  // 回归背景：话题只有卡片视图且看不出素材来自哪个采集源，用户无法按源筛选。
  assert.match(studio, /topicViewMode/, '缺少卡片/列表视图切换状态')
  assert.match(studio, /t-radio-button value="card"/, '缺少卡片视图切换')
  assert.match(studio, /t-radio-button value="list"/, '缺少列表视图切换')
  assert.match(studio, /sourceFilter/, '缺少按采集源筛选状态')
  assert.match(studio, /sourceOptions/, '筛选下拉未接线')
  assert.match(studio, /filteredTopics/, '筛选未作用到话题列表')
  assert.match(api, /sources:\s*string\[\]/, 'ArticleTopic 缺少采集源字段')
  assert.match(studio, /topic-card__source/, '卡片未展示采集源标签')
  // 后端契约：话题接口返回采集源（联表 hot_source 去重）
  assert.match(routerSrc, /sources_by_event/, '后端未联表查询采集源')
  assert.match(routerSrc, /sources: list\[str\]/, 'TopicItem 缺少 sources 字段')
})

test('失败任务可重试：检查点续跑 + 启动自动接续', () => {
  // 回归背景：DB 连接中断（OperationalError）/ 服务重启导致任务中断后无法继续。
  assert.match(api, /retryTask/, '缺少失败任务重试接口封装')
  assert.match(api, /\/retry/, '重试接口路径缺失')
  assert.match(studio, /handleRetry/, '前端未接线重试按钮')
  assert.match(routerSrc, /tasks\/\{task_id\}\/retry/, '后端缺少重试路由')
  // 后端：段执行瞬时故障重试，从 checkpoint 续跑而不是从头重来
  assert.match(llmSrc, /def has_checkpoint/, '缺少检查点存在性探测')
  assert.match(llmSrc, /def pending_interrupt/, '缺少审核点还原探测')
  assert.match(llmSrc, /ConnectionPool/, '检查点未用连接池（连接中断无法自动重连）')
  assert.match(
    serviceSrc,
    /step_input = None if await _has_checkpoint/,
    '段重试未从检查点续跑',
  )
  assert.match(serviceSrc, /SEGMENT_MAX_ATTEMPTS/, '缺少段重试上限')
  assert.match(serviceSrc, /async def retry_task/, '缺少失败任务重试服务')
  assert.match(
    serviceSrc,
    /asyncio\.create_task\(\s*run_generation_segment\(row\.task_id/,
    '启动恢复未自动接续中断任务（仍标记失败）',
  )
})

test('审批卡必须左对齐且占满行宽（gen-panel 居中布局回归 bug）', () => {
  // 回归 bug：Step 2 的 gen-panel 是 text-align:center + align-items:center，
  // 审批卡继承后 Markdown 渲染内容整体居中、卡片收缩，可读性极差。
  assert.match(
    studio,
    /\.review-card \{[\s\S]{0,120}width: 100%;[\s\S]{0,200}text-align: left;/,
    '审批卡未拉回左对齐/未占满行宽',
  )
})

test('发布按钮真实接线：复制到剪贴板 + 打开对应自媒体后台', () => {
  assert.match(studio, /handlePublish/, '缺少发布处理函数')
  assert.match(studio, /clipboard\.writeText|execCommand\('copy'\)/, '发布未复制正文')
  assert.match(studio, /mp\.weixin\.qq\.com/, '缺少公众号发布入口')
  assert.match(studio, /baijiahao\.baidu\.com/, '缺少百家号发布入口')
  assert.match(studio, /mp\.toutiao\.com/, '缺少头条发布入口')
  assert.match(studio, /@click="handlePublish"/, '发布按钮未绑定点击事件')
})

test('路由注册了工作台并保留旧预览直达链接', () => {
  assert.match(routes, /name:\s*'article_studio'/, '缺少工作台路由')
  assert.match(routes, /name:\s*'article_preview'/, '旧预览路由丢失，历史链接会 404')
  assert.match(routes, /ArticleStudioView\.vue/, '路由未指向工作台页面')
})

test('markdown-it 声明为前端直接依赖（非幽灵依赖）', () => {
  const parsed = JSON.parse(pkg) as { dependencies: Record<string, string> }
  assert.ok(parsed.dependencies['markdown-it'], 'markdown-it 未列入 frontend/package.json，单独 npm ci 会构建失败')
})

test('文章配图链路：素材有图才配图（封面 + 正文插图 + 跨源地址重写）', () => {
  const illustrateSrc = readRepo('backend/app/article/illustrate.py')
  // 后端：封面选择 + 正文/文章类平台版本插图 + cover_image 落库
  assert.match(illustrateSrc, /def illustrate_state/, '缺少配图后处理入口')
  assert.match(illustrateSrc, /def pick_cover/, '缺少封面选择')
  assert.match(illustrateSrc, /MAX_INLINE_IMAGES/, '缺少正文插图数量上限')
  assert.match(illustrateSrc, /def insert_images[\s\S]*幂等/, '正文插图需幂等（重跑不重复插入）')
  assert.match(modelsSrc, /cover_image/, 'Article 表缺少封面字段')
  assert.match(serviceSrc, /illustrate\.illustrate_state/, '落库前未做配图后处理')
  assert.match(serviceSrc, /migrate_article_columns/, '存量库缺少 cover_image 补列迁移')
  // 前端：ArticleDetail 带封面；预览把封面置于正文最前
  assert.match(api, /cover_image: string/, 'ArticleDetail 缺少封面字段')
  assert.match(studio, /article\.value\.cover_image/, '预览未使用封面图')
  assert.match(studio, /!\[封面\]\(\$\{cover\}\)/, '封面未置于正文最前')
  // 跨源部署（VITE_API_BASE_URL）时图片地址必须补 API 根前缀，否则全部 404
  assert.match(studio, /function resolveImageUrls/, '缺少图片地址解析')
  assert.match(studio, /cloudConfig\(\)\.apiBase/, '图片地址解析未考虑 API 根前缀')
})
