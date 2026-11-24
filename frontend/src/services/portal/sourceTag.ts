/**
 * 出站链接的 utm 来源标记。
 *
 * 通过本系统跳转到外部应用时统一带 `?utm_source=alsoapp.com`，让目标站点
 * 能识别流量来自 AlsoApps 门户。纯函数，便于 Node 单测覆盖各种 URL 形态。
 *
 * 规则：
 *  - 只处理绝对 http(s) 链接；本站相对路径（/xxx）、mailto:、锚点等原样返回；
 *  - 已有任意 utm_source（大小写不敏感）时不覆盖，避免重复；
 *  - 保留原有 query / hash，utm 参数插在 hash 之前；
 *  - 非法 URL 原样返回，绝不因拼接失败阻断跳转。
 */
export const UTM_SOURCE = 'alsoapp.com'

export function withSourceTag(url: string): string {
  const raw = (url ?? '').trim()
  if (!raw) return raw

  // 相对路径 / 协议相对 / 非 http(s)（mailto、tel、data、javascript 等）不加
  if (!/^https?:\/\//i.test(raw)) return raw

  let parsed: URL
  try {
    parsed = new URL(raw)
  } catch {
    return raw
  }

  // 已带 utm_source（任意值）则尊重原值，不覆盖
  for (const key of parsed.searchParams.keys()) {
    if (key.toLowerCase() === 'utm_source') return raw
  }

  parsed.searchParams.set('utm_source', UTM_SOURCE)
  return parsed.toString()
}
