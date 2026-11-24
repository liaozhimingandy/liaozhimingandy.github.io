-- 011: 应用目录新增「即将下线」标识字段
--
-- 用于后台给应用打标，前台卡片/详情页展示提醒。
-- 幂等：列已存在则跳过，可安全重复执行。

ALTER TABLE portal_apps
    ADD COLUMN IF NOT EXISTS is_offline_soon BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN portal_apps.is_offline_soon IS '即将下线标识：true 时前台展示下线提醒';
