-- 009: SafeKeep 路由从 /tools/safekeep/ 回退到 /safekeep/
--
-- 背景：/tools/ 前缀在 www.alsoapp.com 的 ESA CDN 上被单独回源到旧 tools 站点，
-- /tools/safekeep/ 返回 GitHub 原生 "Site not found"，请求到不了本站。故恢复
-- 使用根路径 /safekeep/（CDN 劫持仅针对 /tools/ 前缀，根路径正常）。
--
-- 幂等：仅命中仍为 /tools/safekeep/ 的记录；已是 /safekeep/ 的库重复执行无副作用。
-- 若此前从未执行过旧版 008，本迁移不会产生任何变更。

UPDATE portal_apps
SET launch_url = '/safekeep/', updated_at = now()
WHERE launch_url = '/tools/safekeep/';
