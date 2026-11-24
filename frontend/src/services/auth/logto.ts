/**
 * Logto 登录态封装（@logto/browser 3.1.2）。
 *
 * 设计要点：
 *  1. 未配置（VITE_LOGTO_ENDPOINT / APP_ID 缺失）时全部降级为空操作，
 *     绝不 new LogtoClient、绝不跳转，保证 Pages 上纯本地模式照常可用、不白屏。
 *  2. OAuth 回调落在站点根（如 /tools/?code=..&state=..）。hash 路由会在模块
 *     导入阶段自动补 '#/'，故交给 SDK 前必须用 oauthCallbackUrl() 剥掉 fragment
 *     （详见 callback.ts）。无论回调成功失败都清理 query，避免刷新重放。
 *  3. 只向业务层暴露 sub / accessToken / isAuthenticated，不触碰主密码与 vaultKey。
 *  4. 不再用「本次是否刚消费回调」这种易失的模块级标志去 gate 云端恢复：
 *     二次跳转、刷新、SDK 异步就绪都会让它丢失。恢复意图本身带 TTL 且一次性消费，
 *     由 useSafeKeep 依据「意图 + 已登录」续做，才是可闭环的判据。
 */
import LogtoClient from '@logto/browser'
import { logtoConfig, type LogtoConfig } from '@/config.ts'
import { isCallbackError, oauthCallbackUrl } from './callback.ts'

let client: LogtoClient | null = null
/** main.ts 在挂载前 initAuth() 的结果缓存，供各视图同步读取初始登录态。 */
let lastAuthState: AuthState | null = null

/** 静默登录探测的会话标记：登录入口发起 prompt=none 时置位，回调落地后消费。 */
const SILENT_PROBE_KEY = 'ap-logto-silent-probe'

function markSilentProbe(): void {
  try { sessionStorage.setItem(SILENT_PROBE_KEY, '1') } catch { /* 隐私模式忽略 */ }
}
/** 读取并清除静默探测标记（一次性消费，避免影响后续普通登录）。 */
function consumeSilentProbe(): boolean {
  try {
    const v = sessionStorage.getItem(SILENT_PROBE_KEY) === '1'
    sessionStorage.removeItem(SILENT_PROBE_KEY)
    return v
  } catch {
    return false
  }
}

function cfg(): LogtoConfig {
  return logtoConfig()
}

/** 同步读取最近一次 initAuth 的登录态（挂载前已就绪），避免视图重复走回调逻辑。 */
export function cachedAuthState(): AuthState | null {
  return lastAuthState
}

/** 惰性构造客户端；未配置返回 null（降级信号）。 */
function getClient(): LogtoClient | null {
  if (!cfg().enabled) return null
  if (client === null) {
    const c = cfg()
    client = new LogtoClient(
      {
        endpoint: c.endpoint,
        appId: c.appId,
        resources: c.resource ? [c.resource] : [],
        scopes: c.scopes,
        requestTimeoutMs: 10000,
      },
      true, // enableCache：sessionStorage 缓存 discovery，减少重复请求
    )
  }
  return client
}

export interface AuthState {
  configured: boolean
  authenticated: boolean
  sub: string | null
}

/** 是否配置了可用的 Logto 登录。 */
export function isConfigured(): boolean {
  return cfg().enabled
}

/** 当前 URL 是否是 OAuth 回调（带 code/state）。供启动时判断是否要消费。 */
export function hasCallbackParams(): boolean {
  if (typeof window === 'undefined') return false
  const q = new URLSearchParams(window.location.search)
  return q.has('code') && q.has('state')
}

/**
 * 启动序列：若当前 URL 带 code/state 则消费回调，然后返回最新登录态。
 * 必须在 createApp().mount() 之前 await，保证回调完成后 UI 读到的是已登录态，
 * 且 URL 里的临时参数已清理（刷新不会再触发一次 handleSignInCallback）。
 * 任何异常都吞掉并降级为未登录，绝不阻断应用挂载。
 *
 * 静默登录回退：点登录先用 prompt=none 探测 Logto 会话；无会话时 Logto 回跳带
 * error=login_required，这里识别「error 回调 + 静默标记」后回退到交互登录页。
 * 静默标记一次性消费，因此交互登录被取消产生的 error 不会再回退（无死循环）。
 */
export async function initAuth(): Promise<AuthState> {
  let c: LogtoClient | null
  try {
    c = getClient()
  } catch {
    // 配置有误（如 endpoint 非法）导致构造失败，降级为未配置，绝不阻断挂载
    lastAuthState = { configured: false, authenticated: false, sub: null }
    return lastAuthState
  }
  if (!c) {
    lastAuthState = { configured: false, authenticated: false, sub: null }
    return lastAuthState
  }
  const isCallback = hasCallbackParams()
  const isErrorCallback = typeof window !== 'undefined' && isCallbackError(window.location.href)
  // 一次性消费静默探测标记：无论本次是成功、失败还是普通访问都清掉，
  // 避免残留标记把后续「交互登录取消」误判为静默失败（防循环的关键）。
  const wasSilentProbe = consumeSilentProbe()

  // 静默探测失败：error 回调 + 本次来自静默探测 → 清理参数后回退到交互登录。
  if (isErrorCallback && wasSilentProbe) {
    stripCallbackParams()
    lastAuthState = { configured: true, authenticated: false, sub: null }
    try {
      await c.signIn({ redirectUri: cfg().redirectUri }) // 交互登录，会跳转离开页面
    } catch { /* 跳转失败则维持未登录态，不阻断挂载 */ }
    return lastAuthState
  }

  try {
    if (isCallback) {
      // 关键：vue-router 的 hash history 已把回调 URL 补成 ...?state=xyz#/，
      // 直接传 window.location.href 会让 SDK 把 '#/' 当成 state 的一部分。
      await c.handleSignInCallback(oauthCallbackUrl(window.location.href))
    }
    const authed = await c.isAuthenticated()
    const sub = authed ? (await c.getIdTokenClaims()).sub : null
    lastAuthState = { configured: true, authenticated: authed, sub: sub ?? null }
    return lastAuthState
  } catch {
    lastAuthState = { configured: true, authenticated: false, sub: null }
    return lastAuthState
  } finally {
    // 成功或失败都要清掉临时参数：失败时若保留 code/state，刷新会反复重放同一次回调。
    if (isCallback || isErrorCallback) stripCallbackParams()
  }
}

/** 去掉 URL 里的 code/state/iss 等临时参数，保留 hash 路由，避免刷新重放。 */
function stripCallbackParams(): void {
  if (typeof window === 'undefined') return
  const url = new URL(window.location.href)
  for (const k of ['code', 'state', 'iss', 'session_state', 'error', 'error_description']) {
    url.searchParams.delete(k)
  }
  const clean = url.pathname + url.search + url.hash
  window.history.replaceState(window.history.state, '', clean)
}

/**
 * 发起登录。
 *
 * 默认 silent=true：先用 prompt=none 探测 Logto 统一会话——
 *  - 已在 Logto 登录（含其它 app 建立的会话）：免密直接带回 code，initAuth 消费即登录；
 *  - 未登录：Logto 回跳带 error，initAuth 识别静默标记后回退到交互登录页。
 * 探测只是一次无 UI 的跳转，用户无感知，符合 SSO 预期。
 *
 * silent=false 用于 initAuth 的回退与显式强制登录场景，直接走带交互的常规登录。
 */
export async function signIn(silent = true): Promise<void> {
  const c = getClient()
  if (!c) return
  if (silent) markSilentProbe()
  const options = silent
    ? { redirectUri: cfg().redirectUri, prompt: 'none' }
    : { redirectUri: cfg().redirectUri }
  try {
    await c.signIn(options)
  } catch (e) {
    // 静默探测跳转失败：清掉标记，避免残留标记影响下次登录
    if (silent) consumeSilentProbe()
    throw e
  }
}

/**
 * 退出「本系统」：只清本地 token，不触碰 Logto 统一会话。
 *
 * 刻意不调用 SDK 的 signOut()——后者会跳到 Logto 的 end-session 端点清除统一会话，
 * 导致所有共享该会话的 app 一起被登出。这里仅清本地凭证后回跳本站落地页，
 * 其它 app 的会话与本地登录态均不受影响；下次点登录仍可静默恢复本系统登录态。
 */
export async function signOut(): Promise<void> {
  const c = getClient()
  if (!c) {
    lastAuthState = { configured: false, authenticated: false, sub: null }
    return
  }
  await c.clearAllTokens()
  lastAuthState = { configured: true, authenticated: false, sub: null }
  // 回跳本站落地页触发各视图重新读取登录态；不经过 Logto，不影响统一会话
  if (typeof window !== 'undefined') {
    window.location.assign(cfg().postLogoutRedirectUri)
  }
}

/** 当前是否已登录。 */
export async function isAuthenticated(): Promise<boolean> {
  const c = getClient()
  if (!c) return false
  try {
    return await c.isAuthenticated()
  } catch {
    return false
  }
}

/** 当前用户 sub（未登录返回 null）。 */
export async function currentSub(): Promise<string | null> {
  const c = getClient()
  if (!c) return null
  try {
    if (!(await c.isAuthenticated())) return null
    return (await c.getIdTokenClaims()).sub ?? null
  } catch {
    return null
  }
}

/** access token 提供器；供 client.ts 作为 Bearer 附带，切 logto 模式时后端会校验。 */
export async function currentAccessToken(): Promise<string | null> {
  const c = getClient()
  if (!c) return null
  try {
    if (!(await c.isAuthenticated())) return null
    return await c.getAccessToken(cfg().resource || undefined)
  } catch {
    return null
  }
}

/** 用户展示信息（昵称/邮箱），仅用于 UI，不构成身份判据。 */
export interface DisplayUser {
  sub: string
  name: string
  email: string
  picture: string
}
export async function displayUser(): Promise<DisplayUser | null> {
  const c = getClient()
  if (!c) return null
  try {
    if (!(await c.isAuthenticated())) return null
    const claims = await c.getIdTokenClaims()
    return {
      sub: claims.sub,
      name: String(claims.name ?? claims.username ?? ''),
      email: String(claims.email ?? ''),
      picture: String(claims.picture ?? ''),
    }
  } catch {
    return null
  }
}
