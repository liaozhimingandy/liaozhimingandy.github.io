-- 008: SafeKeep 独立工具统一迁入 /tools/ 命名空间
--
-- 背景：站点路由整改后，独立工具统一收在 /tools/<tool>/ 下（如 /tools/safekeep/），
-- 与官网产品页 /products/*、门户页 /apps/* 区分开。前端 router 已把 /safekeep/
-- 永久重定向到 /tools/safekeep/，本迁移把门户目录里已登记的旧地址同步更新，
-- 保证应用中心卡片、首页九宫格跳转的是新地址。
--
-- 幂等：重复执行无副作用；仅命中 launch_url 仍为旧值的记录。

UPDATE portal_apps
SET launch_url = '/tools/safekeep/', updated_at = now()
WHERE launch_url = '/safekeep/';
