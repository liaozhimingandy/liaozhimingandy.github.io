"""article 包通用工具：链接规范化。"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, unquote, urlencode, urlparse

# 规范化链接时忽略的常见跟踪参数（大小写不敏感）
_TRACKING_PARAM_RE = re.compile(
    r"^(utm_.*|spm|from|src|source|ref|referer|share_.*|_source|isappinstalled|scene|clicktime)$",
    re.IGNORECASE,
)


def normalize_news_url(url) -> str:
    """把新闻链接规范化成去重 key。

    统一 http/https 与 www、去掉锚点、默认端口和常见跟踪参数，
    这样同一篇文章换了分享参数也不会被重复采集。保留有实际意义 query。
    """
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        if parsed.scheme.lower() not in ("http", "https"):
            return ""
        host = (parsed.hostname or "").lower()
        if not host:
            return ""
        try:
            port = parsed.port
        except ValueError:
            port = None
        if port and port not in (80, 443):
            host = f"{host}:{port}"
        if host.startswith("www."):
            host = host[4:]

        path = unquote(parsed.path or "")
        path = re.sub(r"/{2,}", "/", path)
        if path != "/":
            path = path.rstrip("/") or "/"

        pairs = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=False)
            if not _TRACKING_PARAM_RE.match(key)
        ]
        pairs.sort()
        query = urlencode(pairs, doseq=True)
        return "https://" + host + path + (f"?{query}" if query else "")
    except Exception:
        return raw
