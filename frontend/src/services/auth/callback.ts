/**
 * OAuth 回调 URL 归一化（纯函数，不依赖 SDK / DOM，可在 node --test 直测）。
 *
 * 真实根因（本地点「登录并从云端恢复」不闭环）：
 *  前端用 createWebHashHistory()。OAuth 回调落在站点根时 URL 没有 fragment，
 *  vue-router 在**模块导入阶段**就会 history.replaceState 补上 '#/'：
 *      /tools/?code=abc&state=xyz   →   /tools/?code=abc&state=xyz#/
 *  而 @logto/js 的 verifyAndParseCodeFromCallbackUri() 用 `uri.split('?')`
 *  把整段尾部交给 URLSearchParams，fragment 会粘在最后一个参数值上：
 *      state = 'xyz#/'   ≠   signIn 时保存的 'xyz'
 *  → callback_uri_verification.state_mismatched → handleSignInCallback 抛错
 *  → initAuth 降级为「未登录」→ 恢复意图被清掉 → 用户看到的就是「点了没反应」。
 *
 * 修法：交给 SDK 的回调 URL 只保留 origin + pathname + search，显式剥掉 fragment。
 * OAuth2 的 redirect_uri 本就禁止带 fragment，SDK 也只用 callbackUri.startsWith(redirectUri)
 * 校验前缀，因此去掉 fragment 完全符合协议，并让登录链路与 hash 路由彻底解耦。
 */
export function oauthCallbackUrl(href: string): string {
  const u = new URL(href)
  return u.origin + u.pathname + u.search
}

/**
 * 从回调 URL 读取查询参数（纯函数，显式忽略 fragment）。
 * hash 路由会给回调补 '#/'，用 new URL().search 天然只取 '?' 与 '#' 之间的部分，
 * 不受 fragment 污染；供「静默登录失败回调」检测复用同一套归一化规则。
 */
export function callbackQuery(href: string): URLSearchParams {
  return new URL(href).searchParams
}

/**
 * 当前 URL 是否是 Logto 的错误回调（prompt=none 探测无会话时会回跳带 error）。
 * 只要带 error 参数即判定，不挑具体错误码——静默探测失败一律回退到交互登录页。
 */
export function isCallbackError(href: string): boolean {
  return callbackQuery(href).has('error')
}
