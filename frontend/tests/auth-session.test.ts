/**
 * Logto 登录/退出契约测试（node --test）。
 *
 * 回归背景（2026-11-24）：
 *  1) 统一门户点退出调用了 SDK 的 signOut()，它会跳 Logto end-session 端点清除
 *     **统一会话**，导致所有共享该会话的 app 一起被登出。正确做法是只清本系统
 *     本地 token（clearAllTokens），不触碰服务端会话。
 *  2) 点登录应先静默探测 Logto 会话（prompt=none）：已登录免密直接进入，未登录
 *     回跳 error 后回退交互登录页。用户不必在已有会话时重新输入密码。
 *
 * 纯函数（callback.ts）直接 import 断言；涉及 SDK/window 的退出与静默行为用
 * 源码静态守卫，避免未来改动悄悄退回到「远程登出」或去掉 prompt=none。
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { isCallbackError, callbackQuery, oauthCallbackUrl } from '../src/services/auth/callback.ts'

const ROOT = resolve(fileURLToPath(new URL('../..', import.meta.url)))
function read(rel: string): string {
  return readFileSync(resolve(ROOT, rel), 'utf8')
}
const LOGTO_SRC = read('frontend/src/services/auth/logto.ts')

// --------------------------------------------------------------------------- #
// 纯函数：错误回调识别（静默探测失败的判据）
// --------------------------------------------------------------------------- #

test('isCallbackError：识别带 error 的回调，忽略成功回调与普通 URL', () => {
  assert.equal(isCallbackError('https://www.alsoapp.com/?error=login_required&state=s'), true)
  assert.equal(isCallbackError('https://www.alsoapp.com/?error=access_denied&state=s&iss=x'), true)
  assert.equal(isCallbackError('https://www.alsoapp.com/?code=c&state=s'), false)
  assert.equal(isCallbackError('https://www.alsoapp.com/'), false)
  assert.equal(isCallbackError('https://www.alsoapp.com/?code=c&state=s#/'), false)
})

test('isCallbackError：hash 路由补 #/ 后仍能识别 error（search 不受 fragment 污染）', () => {
  const href = 'https://www.alsoapp.com/?error=login_required&state=s#/'
  assert.equal(isCallbackError(href), true)
  assert.equal(callbackQuery(href).get('error'), 'login_required')
  assert.equal(callbackQuery(href).get('state'), 's')
})

test('oauthCallbackUrl：错误回调同样剥掉 fragment，state 不粘 #/', () => {
  const href = 'https://www.alsoapp.com/?error=login_required&state=s#/'
  const clean = oauthCallbackUrl(href)
  assert.equal(clean, 'https://www.alsoapp.com/?error=login_required&state=s')
  assert.equal(callbackQuery(clean).get('state'), 's')
})

// --------------------------------------------------------------------------- #
// 源码守卫：本系统退出不能清 Logto 统一会话
// --------------------------------------------------------------------------- #

test('signOut：只清本地 token，绝不调用 SDK 的 signOut（那会清统一会话）', () => {
  const body = LOGTO_SRC.slice(LOGTO_SRC.indexOf('export async function signOut'))
  assert.match(body, /clearAllTokens\(\)/, '必须用 clearAllTokens 清本地凭证')
  assert.doesNotMatch(body, /\bc\.signOut\(/, '不得再调用 SDK signOut——会清掉 Logto 统一会话')
  assert.match(body, /window\.location\.assign\(cfg\(\)\.postLogoutRedirectUri\)/, '清完本地 token 后回跳本站落地页')
})

test('signIn：默认静默探测（prompt=none），并带交互回退能力', () => {
  const body = LOGTO_SRC.slice(LOGTO_SRC.indexOf('export async function signIn'))
  assert.match(body, /signIn\(silent = true\)/, '默认走静默探测')
  assert.match(body, /prompt: 'none'/, '必须用 prompt=none 探测 Logto 会话')
  assert.match(body, /markSilentProbe\(\)/, '静默探测要置一次性标记')
})

test('initAuth：识别 error + 静默标记后回退交互登录，且只回退一次', () => {
  const body = LOGTO_SRC.slice(
    LOGTO_SRC.indexOf('export async function initAuth'),
    LOGTO_SRC.indexOf('/** 去掉 URL 里的'),
  )
  assert.match(body, /isCallbackError\(/, '必须检测 error 回调')
  assert.match(body, /consumeSilentProbe\(\)/, '必须一次性消费静默标记')
  assert.match(body, /isErrorCallback && wasSilentProbe/, '仅静默探测失败的 error 才回退')
  assert.match(body, /c\.signIn\(\{ redirectUri: cfg\(\)\.redirectUri \}\)/, '回退走交互登录（无 prompt=none）')
})
