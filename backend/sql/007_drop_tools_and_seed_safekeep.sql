-- 007: 下线 tools 注册表，工具准入统一以 portal_apps 为权威
--
-- 背景：tools 表是早期的独立「工具注册表」（tool_id/配额覆盖），与 portal_apps
-- 职责重叠。本轮起 configs 接口的 tool_id 准入语义改为「portal_apps 中存在该
-- code 且 status=published 的应用」，tools 表不再被任何代码访问，物理删除。
--
-- 同时补种 SAFEKEEP（锦囊）门户应用：它是 configs 接口唯一在用的 tool_id，
-- 必须在 portal_apps 中存在且已发布，否则 /v1/configs/* 全部 404。
-- 若该 code 已存在（例如已通过管理后台手工创建），保留现有记录不覆盖。

DROP TABLE IF EXISTS tools;

INSERT INTO portal_apps
    (code, name, subtitle, description, detail, icon_url, cover_url, launch_url,
     app_type, open_mode, status, visibility, auth_required, is_featured, show_on_home, is_new, sort_order, published_at)
VALUES
    ('SAFEKEEP', '锦囊 SafeKeep', '零知识在线密码保险库',
     '浏览器端 AES-256-GCM 加密，主密码与恢复码双钥匙解锁，服务端只保存密文。',
     '锦囊 SafeKeep：零知识在线密码保险库。数据在浏览器端加密后才上传，服务端只保存密文，主密码与恢复码双钥匙解锁。',
     '', '', '/safekeep/',
     'tool', 'new_tab', 'published', 'public', FALSE, TRUE, FALSE, FALSE, 5, now())
ON CONFLICT (code) DO NOTHING;

COMMENT ON TABLE portal_apps IS 'Also Apps 门户应用目录；展示与导航、工具准入的唯一数据源，不含业务授权';
