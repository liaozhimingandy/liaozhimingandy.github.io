/**
 * 自媒体热点文章流水线 API 客户端（/v1/articles/*）。
 *
 * 与 portal/api.ts 共用同一套鉴权头、超时与错误摊平机制（PortalApiError），
 * 前端不硬编码任何话题/文章数据，全部来自后端流水线：
 *   话题列表 -> 触发生成（异步任务）-> 轮询任务状态 -> 读取文章详情 -> 预览/复制。
 *
 * 契约来源：backend/app/article/router.py。
 */

import { jsonBody, PortalApiError, request } from './api.ts'

/** 可选话题（后端 ArticleEvent 聚合视图） */
export interface ArticleTopic {
  event_id: number
  event_title: string
  event_summary: string
  total_score: number
  status: string
  source_urls: string[]
  images: Array<Record<string, unknown>>
  /** 该话题是否已有进行中的生成任务 */
  generating: boolean
  /** 素材的采集源（如 百度/微博/36氪），去重保序；用于展示标签与筛选 */
  sources: string[]
}

/** 审核决定 */
export type ReviewDecision = 'pass' | 'modify' | 'reject'

/** 生成任务状态（后端 GenerationTask）
 * 状态机：queued -> running -> waiting_approval -> running -> ... -> done / failed
 * waiting_approval 时 review_* 字段携带待审内容，供前端渲染审批卡。
 */
export interface GenerationTask {
  task_id: string
  event_id: number
  event_title: string
  status: 'queued' | 'running' | 'waiting_approval' | 'done' | 'failed'
  error: string
  thread_id: string
  article_id: number
  article_uuid: string
  /** 当前执行到哪一步（工作流节点名，如 generate_draft / review / done） */
  current_step: string
  /** 是否人工审核（重启续跑/重试时后端用这个重建首段输入） */
  need_review: boolean
  created_at: string
  started_at: string
  finished_at: string
  /** HITL 待审信息（status=waiting_approval 时有值） */
  review_stage: string
  review_title: string
  review_content: string
  review_options: ReviewDecision[]
}

/** 文章详情（后端 Article 表模型公共视图，字段 exclude_none） */
export interface ArticleDetail {
  id: number
  event_id: number
  event_title: string | null
  outline: string
  draft: string
  /** 多平台版本：official(公众号) / baijia / toutiao / xiaohongshu / script / title_list / cover_prompt */
  multi_platform: Record<string, string | string[]>
  check_report: string
  final_article: string
  /** 封面图（后端从素材图选出的 /images/... 路径；素材无图时为空串） */
  cover_image: string
  images: unknown[]
  source_urls: string[]
  model: string
  status: string
  is_current: boolean
  thread_id: string | null
  uuid: string
  create_time: string
  update_time: string
}

/** 调度器状态（管理员可见，本页仅展示采集/聚合概况） */
export interface SchedulerStatus {
  running: boolean
  collect: Record<string, unknown>
  cluster: Record<string, unknown>
  [key: string]: unknown
}

/** ① 话题列表：公开可读 */
export function listTopics(limit = 50): Promise<{ items: ArticleTopic[]; total: number }> {
  return request(`/v1/articles/topics?limit=${limit}`)
}

/** ② 触发生成：立即返回任务，前端需轮询 task 状态。
 * needReview：是否人工审核（大纲/终审）；不传时由后端 ARTICLE_HITL_ENABLED 配置决定。
 */
export function generateArticle(eventId: number, needReview?: boolean): Promise<GenerationTask> {
  return request('/v1/articles/generate', {
    method: 'POST',
    ...jsonBody({ event_id: eventId, need_review: needReview ?? null }),
  })
}

/** ③ 查询单个任务状态：done 时带 article_uuid */
export function getTask(taskId: string): Promise<GenerationTask> {
  return request(`/v1/articles/tasks/${encodeURIComponent(taskId)}`)
}

/** ③-b HITL 审批：提交决定后从断点恢复工作流 */
export function reviewTask(
  taskId: string,
  decision: ReviewDecision,
  suggest = '',
): Promise<GenerationTask> {
  return request(`/v1/articles/tasks/${encodeURIComponent(taskId)}/review`, {
    method: 'POST',
    ...jsonBody({ decision, suggest }),
  })
}

/** ③-c 失败任务重试：有检查点从报错节点续跑，否则从头跑首段 */
export function retryTask(taskId: string): Promise<GenerationTask> {
  return request(`/v1/articles/tasks/${encodeURIComponent(taskId)}/retry`, {
    method: 'POST',
  })
}

/** 最近任务列表（用于任务历史回看） */
export function listTasks(limit = 20): Promise<{ items: GenerationTask[] }> {
  return request(`/v1/articles/tasks?limit=${limit}`)
}

/** 文章列表（不含正文大字段） */
export function listArticles(params: { eventId?: number; limit?: number } = {}): Promise<{
  items: Array<{ uuid: string; event_id: number; event_title: string | null; status: string; create_time: string }>
  total: number
}> {
  const q = new URLSearchParams()
  if (params.eventId) q.set('event_id', String(params.eventId))
  if (params.limit) q.set('limit', String(params.limit))
  const suffix = q.toString() ? `?${q}` : ''
  return request(`/v1/articles${suffix}`)
}

/** 文章详情：多平台正文、图片、来源都在这里 */
export function getArticle(uuid: string): Promise<ArticleDetail> {
  return request(`/v1/articles/${encodeURIComponent(uuid)}`)
}

/** 调度器状态（管理员接口；普通用户调用会得到 403，由调用方吞掉） */
export function getSchedulerStatus(): Promise<SchedulerStatus> {
  return request('/v1/articles/scheduler')
}

export { PortalApiError }
