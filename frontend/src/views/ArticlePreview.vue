<script setup lang="ts">
/**
 * ArticlePreview —— 多平台文章排版预览组件
 *
 * 职责：
 *   1. 公众号 / 百家号 / 今日头条 三平台 Tab 切换（切换时 emit change 通知父组件，
 *      由父组件向 LangGraph 后端请求对应平台的内容，本组件不做任何内容修改）
 *   2. Markdown（GFM：表格 / 删除线 / 硬换行）渲染 + 图片图注重写
 *   3. 三套独立排版样式（scoped + :deep() 隔离，不污染全局）
 *   4. 一键复制「带内联样式的成品 HTML」，可直接粘贴到自媒体后台编辑器
 *
 * 说明：
 *   - markdown-it 内核已实现 GFM（表格、删除线），开启 breaks 即可支持单换行转 <br>，
 *     无需再引入已停更的 markdown-it-gfm 插件，避免旧插件与新内核冲突。
 *   - html: false 禁止 Markdown 里的原生 HTML 直出，防止后端素材被注入脚本。
 *   - 仅做预览与复制，禁止编辑：内容修改走后端 LangGraph interrupt 人工审核节点。
 */
import { computed, onUnmounted, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'

/** 平台标识：与后端 state.multi_platform 的字段一一对应 */
type Platform = 'wechat' | 'baijia' | 'toutiao'

interface Props {
  /** 当前预览的平台 */
  platform: Platform
  /** 平台正文，标准 Markdown（GFM），图片语法 ![图注](url) */
  mdContent: string
  /** 文章标题（仅展示，不参与复制内容） */
  title: string
}

const props = defineProps<Props>()

/** 切换平台时通知父组件：父组件据此切换 mdContent 数据源 */
const emit = defineEmits<{
  change: [platform: Platform]
}>()

defineOptions({ name: 'ArticlePreview' })

/* ==================== 1. 平台 Tab ==================== */

const PLATFORM_TABS: ReadonlyArray<{ key: Platform; label: string }> = [
  { key: 'wechat', label: '公众号' },
  { key: 'baijia', label: '百家号' },
  { key: 'toutiao', label: '今日头条' },
]

/** 内部激活 Tab；props.platform 变化（父组件驱动）时自动跟随 */
const activePlatform = ref<Platform>(props.platform)
watch(
  () => props.platform,
  (next) => { activePlatform.value = next },
)

function handleTabClick(platform: Platform): void {
  if (activePlatform.value === platform) return
  activePlatform.value = platform
  emit('change', platform)
}

/* ==================== 2. Markdown 渲染 ==================== */

/** markdown-it Token 的最小结构描述（避免耦合不同版本的内部类型路径） */
interface MdTokenLike {
  type: string
  content: string
  children: MdTokenLike[] | null
  attrGet: (name: string) => string | null
}

const md = new MarkdownIt({
  html: false,     // 禁止原生 HTML 直出，防注入
  breaks: true,    // GFM：单换行渲染为 <br>
  linkify: true,   // 自动识别链接
})

/** 提取图片 alt 文本：markdown-it 把 alt 解析进 image token 的 children */
function getImageAlt(token: MdTokenLike): string {
  if (!token.children) return ''
  return token.children
    .filter((child) => child.type === 'text' || child.type === 'code_inline')
    .map((child) => child.content)
    .join('')
    .trim()
}

/**
 * 重写图片渲染：alt 作为图片下方图注（figcaption）。
 * 输出 <figure><img><figcaption> 结构，图注样式见 <style> 的 :deep(.ap-figcaption)。
 */
md.renderer.rules.image = (tokens, idx): string => {
  const token = tokens[idx] as unknown as MdTokenLike
  const src = md.utils.escapeHtml(token.attrGet('src') ?? '')
  const alt = md.utils.escapeHtml(getImageAlt(token))
  const caption = alt
    ? `<figcaption class="ap-figcaption">${alt}</figcaption>`
    : ''
  return (
    `<figure class="ap-figure">` +
    `<img class="ap-img" src="${src}" alt="${alt}" loading="lazy" />` +
    `${caption}</figure>`
  )
}

/** 判断一个 inline 段落是否「只含图片」（无其他文字） */
function isImageOnlyInline(token: MdTokenLike): boolean {
  const children = token.children ?? []
  const meaningful = children.filter(
    (child) => !(child.type === 'text' && !child.content.trim()),
  )
  return meaningful.length > 0 && meaningful.every((child) => child.type === 'image')
}

/**
 * 独占一段的图片不再包 <p>，让 <figure> 直接落在外层，
 * 避免 <p><figure> 非法嵌套导致后台编辑器粘贴时被改写结构。
 */
md.renderer.rules.paragraph_open = (tokens, idx, options, _env, self): string => {
  const next = tokens[idx + 1]
  if (next && next.type === 'inline' && isImageOnlyInline(next as unknown as MdTokenLike)) {
    return ''
  }
  return self.renderToken(tokens, idx, options)
}
md.renderer.rules.paragraph_close = (tokens, idx, options, _env, self): string => {
  const prev = tokens[idx - 1]
  if (prev && prev.type === 'inline' && isImageOnlyInline(prev as unknown as MdTokenLike)) {
    return ''
  }
  return self.renderToken(tokens, idx, options)
}

/** 是否有可渲染的内容（空白内容容错：不渲染、不报错） */
const hasContent = computed<boolean>(() => !!(props.mdContent && props.mdContent.trim()))

/** 渲染结果 HTML；渲染异常时降级为错误提示，不抛出阻断页面 */
const renderedHtml = computed<string>(() => {
  if (!hasContent.value) return ''
  try {
    return md.render(props.mdContent)
  } catch (error) {
    console.error('[ArticlePreview] Markdown 渲染失败：', error)
    return '<p>⚠️ 内容渲染失败，请检查 Markdown 格式</p>'
  }
})

/* ==================== 3. 复制排版 HTML ==================== */

/**
 * 公共内联样式（复制专用）：公众号等后台编辑器会剥离 class，
 * 必须把排版样式写成内联 style 才能在粘贴后保留。
 */
const BASE_COPY_STYLES: Readonly<Record<string, string>> = {
  blockquote: 'margin:0 0 16px;padding:12px 16px;background:#f5f6f7;border-left:3px solid #d0d7de;color:#555;',
  figure: 'margin:16px 0;text-align:center;',
  img: 'max-width:100%;height:auto;',
  figcaption: 'margin-top:6px;font-size:12px;color:#999;text-align:center;',
  table: 'width:100%;border-collapse:collapse;margin:0 0 16px;font-size:14px;',
  th: 'border:1px solid #e1e4e8;padding:8px 12px;background:#f7f8fa;',
  td: 'border:1px solid #e1e4e8;padding:8px 12px;',
  hr: 'border:none;border-top:1px solid #e1e4e8;margin:24px 0;',
  a: 'color:#1a6eeb;',
  s: 'color:#999;',
  del: 'color:#999;',
  code: 'background:#f2f3f5;padding:2px 5px;border-radius:3px;font-size:13px;',
  pre: 'background:#f6f8fa;padding:12px;border-radius:6px;overflow:auto;',
}

/** 无首行缩进平台的文本样式（百家号 / 头条，行高 1.7） */
function plainTextStyles(lineHeight: string): Record<string, string> {
  return {
    p: `font-size:16px;line-height:${lineHeight};margin:0 0 14px;color:#333;`,
    h1: `font-size:22px;line-height:1.4;margin:26px 0 16px;color:#1f2328;`,
    h2: `font-size:19px;line-height:1.45;margin:24px 0 14px;color:#1f2328;`,
    h3: `font-size:17px;line-height:1.45;margin:20px 0 12px;color:#1f2328;`,
    h4: `font-size:16px;line-height:1.5;margin:18px 0 12px;color:#1f2328;`,
    ul: `margin:0 0 14px;padding-left:1.6em;line-height:${lineHeight};`,
    ol: `margin:0 0 14px;padding-left:1.6em;line-height:${lineHeight};`,
    li: `line-height:${lineHeight};`,
  }
}

/** 各平台复制用内联样式表：与预览样式保持一致 */
const COPY_INLINE_STYLES = {
  // 公众号（主样式）：段落首行缩进 2em、行高 1.75、h2 蓝色竖线
  wechat: {
    ...BASE_COPY_STYLES,
    p: 'font-size:15px;line-height:1.75;text-indent:2em;margin:0 0 14px;color:#333;',
    h1: 'font-size:22px;line-height:1.4;margin:26px 0 16px;color:#1f2328;',
    h2: 'font-size:20px;line-height:1.45;margin:26px 0 16px;padding-left:12px;border-left:4px solid #1a6eeb;color:#1f2328;',
    h3: 'font-size:18px;line-height:1.45;margin:22px 0 14px;color:#1f2328;',
    h4: 'font-size:16px;line-height:1.5;margin:20px 0 12px;color:#1f2328;',
    ul: 'margin:0 0 14px;padding-left:1.6em;line-height:1.75;',
    ol: 'margin:0 0 14px;padding-left:1.6em;line-height:1.75;',
    li: 'line-height:1.75;',
  },
  // 百家号 / 头条：不缩进、行高 1.7
  baijia: { ...BASE_COPY_STYLES, ...plainTextStyles('1.7') },
  toutiao: { ...BASE_COPY_STYLES, ...plainTextStyles('1.7') },
} as const satisfies Record<Platform, Record<string, string>>

/**
 * 把渲染后的 HTML 加上当前平台的内联样式，得到可直接粘贴的成品 HTML。
 * 注：标题不包含在内——各后台编辑器的标题都是独立输入框。
 */
function buildCopyHtml(): string {
  const rawHtml = renderedHtml.value
  if (!rawHtml) return ''
  try {
    const doc = new DOMParser().parseFromString(`<div id="ap-copy-root">${rawHtml}</div>`, 'text/html')
    const root = doc.getElementById('ap-copy-root')
    if (!root) return rawHtml
    const styleMap: Record<string, string> = COPY_INLINE_STYLES[activePlatform.value]
    const selector = Object.keys(styleMap).join(',')
    root.querySelectorAll<HTMLElement>(selector).forEach((element) => {
      const inlineStyle = styleMap[element.tagName.toLowerCase()]
      if (inlineStyle) element.setAttribute('style', inlineStyle)
    })
    return root.innerHTML
  } catch (error) {
    console.error('[ArticlePreview] 复制 HTML 构建失败，降级为原始渲染结果：', error)
    return rawHtml
  }
}

/** execCommand 兜底复制：非 HTTPS 环境下 navigator.clipboard 不可用 */
function legacyCopy(text: string): boolean {
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  let success = false
  try {
    success = document.execCommand('copy')
  } catch {
    success = false
  }
  document.body.removeChild(textarea)
  return success
}

/* 复制结果提示（友好反馈，2.2s 自动消失） */
const copyState = ref<'success' | 'error'>('success')
const copyMessage = ref('')
let toastTimer: ReturnType<typeof setTimeout> | null = null

function showToast(state: 'success' | 'error', message: string): void {
  copyState.value = state
  copyMessage.value = message
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { copyMessage.value = '' }, 2200)
}

onUnmounted(() => {
  if (toastTimer) clearTimeout(toastTimer)
})

async function handleCopy(): Promise<void> {
  const html = buildCopyHtml()
  if (!html) {
    showToast('error', '暂无内容可复制')
    return
  }
  let success = false
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(html)
      success = true
    }
  } catch {
    success = false
  }
  if (!success) success = legacyCopy(html)
  if (success) {
    showToast('success', '✅ 已复制排版 HTML，可直接粘贴到后台编辑器')
  } else {
    showToast('error', '❌ 复制失败，请手动选择预览内容复制')
  }
}
</script>

<template>
  <section class="ap">
    <!-- 顶部：平台 Tab + 复制按钮 -->
    <header class="ap-header">
      <nav class="ap-tabs" role="tablist" aria-label="平台切换">
        <button
          v-for="tab in PLATFORM_TABS"
          :key="tab.key"
          type="button"
          role="tab"
          class="ap-tab"
          :class="{ 'ap-tab--active': activePlatform === tab.key }"
          :aria-selected="activePlatform === tab.key"
          @click="handleTabClick(tab.key)"
        >
          {{ tab.label }}
        </button>
      </nav>
      <button
        type="button"
        class="ap-copy-btn"
        :disabled="!hasContent"
        @click="handleCopy"
      >
        复制排版HTML
      </button>
    </header>

    <!-- 标题（仅展示；标题不参与复制，后台编辑器单独填写） -->
    <h2 v-if="title" class="ap-title">{{ title }}</h2>

    <!-- 正文预览区：按平台挂排版 class -->
    <div class="ap-body" :class="`ap-body--${activePlatform}`">
      <div v-if="hasContent" class="ap-content" v-html="renderedHtml"></div>
      <div v-else class="ap-empty">暂无内容，等待后端流水线产出…</div>
    </div>

    <!-- 复制结果提示 -->
    <transition name="ap-fade">
      <div v-if="copyMessage" class="ap-toast" :class="`ap-toast--${copyState}`" role="status">
        {{ copyMessage }}
      </div>
    </transition>
  </section>
</template>

<style scoped>
/* ========== 组件骨架：基础边框 + 内边距，视觉干净 ========== */
.ap {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 480px;
  overflow: hidden;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

/* 顶部栏 */
.ap-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  background: #fafbfc;
  border-bottom: 1px solid #eef0f3;
}

.ap-tabs {
  display: flex;
  gap: 8px;
}

.ap-tab {
  padding: 6px 14px;
  font-size: 14px;
  color: #555;
  cursor: pointer;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 16px;
  transition: color 0.2s, background 0.2s, border-color 0.2s;
}

.ap-tab:hover {
  color: #1a6eeb;
}

.ap-tab--active {
  font-weight: 600;
  color: #1a6eeb;
  background: #eaf2ff;
  border-color: #b9d4fb;
}

.ap-copy-btn {
  padding: 7px 16px;
  font-size: 14px;
  color: #fff;
  cursor: pointer;
  background: #1a6eeb;
  border: none;
  border-radius: 6px;
  transition: background 0.2s;
}

.ap-copy-btn:hover:not(:disabled) {
  background: #155dc9;
}

.ap-copy-btn:disabled {
  cursor: not-allowed;
  background: #a5c4f5;
}

/* 标题 */
.ap-title {
  margin: 0;
  padding: 16px 24px 0;
  font-size: 20px;
  line-height: 1.5;
  color: #1f2328;
}

/* 正文容器 */
.ap-body {
  flex: 1;
  padding: 20px 24px 32px;
  overflow: auto;
}

.ap-content {
  margin: 0 auto;
  font-size: 15px;
  color: #333;
  word-break: break-word;
}

/* ========== 平台排版差异 ========== */
/* 公众号（主样式）：最大宽度 670px、首行缩进 2em、行高 1.75、h2 蓝色竖线 */
.ap-body--wechat .ap-content {
  max-width: 670px;
}

.ap-body--wechat :deep(p) {
  line-height: 1.75;
  text-indent: 2em;
  margin: 0 0 14px;
}

.ap-body--wechat :deep(h2) {
  margin: 26px 0 16px;
  padding-left: 12px;
  font-size: 20px;
  line-height: 1.45;
  border-left: 4px solid #1a6eeb;
}

.ap-body--wechat :deep(li) {
  line-height: 1.75;
}

/* 百家号 / 今日头条：最大宽度 720px、不缩进、行高 1.7 */
.ap-body--baijia .ap-content,
.ap-body--toutiao .ap-content {
  max-width: 720px;
}

.ap-body--baijia :deep(p),
.ap-body--toutiao :deep(p) {
  line-height: 1.7;
  text-indent: 0;
  margin: 0 0 14px;
}

.ap-body--baijia :deep(h2),
.ap-body--toutiao :deep(h2) {
  margin: 24px 0 14px;
  font-size: 19px;
  line-height: 1.45;
  border-left: none;
}

.ap-body--baijia :deep(li),
.ap-body--toutiao :deep(li) {
  line-height: 1.7;
}

/* ========== 渲染内容公共样式（v-html 内容必须用 :deep 穿透） ========== */
.ap :deep(h1),
.ap :deep(h3),
.ap :deep(h4) {
  color: #1f2328;
  line-height: 1.45;
}

/* 图注：图片下方小字灰色 */
.ap :deep(.ap-figure) {
  margin: 16px 0;
  text-align: center;
}

.ap :deep(.ap-img) {
  max-width: 100%;
  height: auto;
  border-radius: 4px;
}

.ap :deep(.ap-figcaption) {
  margin-top: 6px;
  font-size: 12px;
  color: #999;
  text-align: center;
}

/* 引用块：浅灰背景 */
.ap :deep(blockquote) {
  margin: 0 0 16px;
  padding: 12px 16px;
  color: #555;
  background: #f5f6f7;
  border-left: 3px solid #d0d7de;
}

.ap :deep(blockquote p) {
  text-indent: 0;
}

/* 表格（GFM） */
.ap :deep(table) {
  width: 100%;
  margin: 0 0 16px;
  font-size: 14px;
  border-collapse: collapse;
}

.ap :deep(th),
.ap :deep(td) {
  padding: 8px 12px;
  text-align: left;
  border: 1px solid #e1e4e8;
}

.ap :deep(th) {
  background: #f7f8fa;
}

/* 列表 / 分隔线 / 其他 */
.ap :deep(ul),
.ap :deep(ol) {
  margin: 0 0 14px;
  padding-left: 1.6em;
}

.ap :deep(hr) {
  margin: 24px 0;
  border: none;
  border-top: 1px solid #e1e4e8;
}

.ap :deep(a) {
  color: #1a6eeb;
}

/* 删除线（GFM：markdown-it 输出 <s>，兼容 <del>） */
.ap :deep(s),
.ap :deep(del) {
  color: #999;
}

.ap :deep(code) {
  padding: 2px 5px;
  font-size: 13px;
  background: #f2f3f5;
  border-radius: 3px;
}

.ap :deep(pre) {
  padding: 12px;
  overflow: auto;
  background: #f6f8fa;
  border-radius: 6px;
}

/* 空内容占位 */
.ap-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 320px;
  font-size: 14px;
  color: #a0a6ad;
}

/* 复制结果提示 */
.ap-toast {
  position: absolute;
  top: 58px;
  left: 50%;
  z-index: 10;
  padding: 8px 16px;
  font-size: 13px;
  border-radius: 6px;
  transform: translateX(-50%);
  box-shadow: 0 4px 12px rgb(0 0 0 / 8%);
}

.ap-toast--success {
  color: #0f8a43;
  background: #e8f7ee;
  border: 1px solid #bfe8cf;
}

.ap-toast--error {
  color: #c0392b;
  background: #fdecec;
  border: 1px solid #f3c1bd;
}

.ap-fade-enter-active,
.ap-fade-leave-active {
  transition: opacity 0.25s, transform 0.25s;
}

.ap-fade-enter-from,
.ap-fade-leave-to {
  opacity: 0;
  transform: translate(-50%, -6px);
}
</style>
