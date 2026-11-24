-- 006: portal_apps.launch_url 放宽支持本站相对路径
--
-- 背景：新增 APP 时访问地址此前只接受 http/https 绝对地址；现在应用可能就是
-- 本站（AP 统一站点）下的一个页面（如 /wedesk/、/apps/xxx/），需要允许相对路径。
-- 前端启动时按当前 origin 解析（window.location.assign / window.open 天然支持）。
--
-- 约束仍保持安全边界：
--   - 空串 = 未部署（草稿），允许；
--   - http/https 绝对地址：必须有主机（沿用 004 正则）；
--   - 相对路径：必须以单个 / 开头（// 开头是 protocol-relative 外站地址，拒绝）；
--     第二个字符不得是 / 或 \；不含空白。
--   - javascript:/data:/file: 等协议依旧被两条正则同时拒绝；
--     Python 层 validate_launch_url 还有更严格的控制字符/反斜杠校验。

ALTER TABLE portal_apps DROP CONSTRAINT IF EXISTS ck_portal_apps_launch_url;

ALTER TABLE portal_apps ADD CONSTRAINT ck_portal_apps_launch_url CHECK (
    launch_url = ''
    OR launch_url ~* '^https?://[^/\s]+(/.*)?$'
    OR launch_url ~ '^/([^/\\][^\\]*)?$'
);

COMMENT ON COLUMN portal_apps.launch_url IS
    'http/https 绝对地址，或以单个 / 开头的本站相对路径；空串表示未部署（草稿）';
