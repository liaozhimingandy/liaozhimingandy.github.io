-- 010: 为 SafeKeep 种子应用补上图标
--
-- 图标文件位于前端 public/static/icons/safekeep.svg，随前端发布到
-- https://www.alsoapp.com/static/icons/safekeep.svg（本站根路径部署）。
--
-- 幂等：只在 icon_url 为空时写入；后台若已手工填过其它图标则不覆盖。
-- 新库执行 007 时已直接带图标，本迁移对其无副作用。

UPDATE portal_apps
SET icon_url = '/static/icons/safekeep.svg', updated_at = now()
WHERE code = 'SAFEKEEP' AND (icon_url IS NULL OR icon_url = '');
