/**
 * 出站跳转来源标记单测（node --test，纯函数无 DOM / 无网络）。
 *
 * 覆盖：外部 http(s) 加 utm_source=alsoapp.com；已有 query / hash 拼接正确；
 * 已有 utm_source 不覆盖；站内相对路径、mailto、非法 URL 原样返回。
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { withSourceTag, UTM_SOURCE } from '../src/services/portal/sourceTag.ts'

test('常量固定为 alsoapp.com', () => {
  assert.equal(UTM_SOURCE, 'alsoapp.com')
})

test('裸外部链接追加 utm_source', () => {
  assert.equal(
    withSourceTag('https://music.openaim.cn'),
    `https://music.openaim.cn/?utm_source=${UTM_SOURCE}`,
  )
})

test('已有 query 用 & 拼接，原有参数保留', () => {
  const out = withSourceTag('https://zaima.alsoapp.com/static/logo.svg?v=2&lang=zh')
  const u = new URL(out)
  assert.equal(u.searchParams.get('v'), '2')
  assert.equal(u.searchParams.get('lang'), 'zh')
  assert.equal(u.searchParams.get('utm_source'), UTM_SOURCE)
})

test('hash 在 utm 之后，不被截断', () => {
  const out = withSourceTag('https://beian.mps.gov.cn/#/query/webSearch?code=44030002019954')
  assert.ok(out.includes(`?utm_source=${UTM_SOURCE}#`))
  assert.ok(out.endsWith('#/query/webSearch?code=44030002019954'))
})

test('已有 utm_source（任意值/大小写）不覆盖', () => {
  assert.equal(
    withSourceTag('https://a.com/?utm_source=partner'),
    'https://a.com/?utm_source=partner',
  )
  assert.equal(
    withSourceTag('https://a.com/?UTM_SOURCE=Partner'),
    'https://a.com/?UTM_SOURCE=Partner',
  )
})

test('站内相对路径不加来源标记', () => {
  assert.equal(withSourceTag('/safekeep/'), '/safekeep/')
  assert.equal(withSourceTag('/apps?view=recent'), '/apps?view=recent')
  assert.equal(withSourceTag('#section'), '#section')
})

test('非 http(s) 协议与非法 URL 原样返回', () => {
  assert.equal(withSourceTag('mailto:contact@alsoapp.com'), 'mailto:contact@alsoapp.com')
  assert.equal(withSourceTag('tel:12345'), 'tel:12345')
  assert.equal(withSourceTag(''), '')
})

test('http 链接同样标记，首尾空格被清理', () => {
  assert.equal(
    withSourceTag('  http://example.org/x  '),
    `http://example.org/x?utm_source=${UTM_SOURCE}`,
  )
})
