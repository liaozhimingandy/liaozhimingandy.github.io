"""Also Apps 门户：UUIDv7 主键生成与 UTC 时间工具。

Python 3.14 已内置 ``uuid.uuid7()``（RFC 9562），本模块不再自行实现 UUIDv7，
只做薄封装再导出，保留既有导入路径（portal/models.py、tests）不破坏。
与 sql/004_apps_portal.sql 的 PG uuidv7() server_default 双保险：
应用侧先生成时间有序 UUID，DB 侧仅在应用未给值时兜底。

时间约定：数据库一律 TIMESTAMPTZ（UTC 时刻）；Python 侧用 aware UTC，
对外 JSON 以 'Z' 结尾；前端展示时转本地时区。
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

# Python 3.14+ 内置；项目 .python-version = 3.14，无需第三方包或手写实现。
uuid7 = uuid.uuid7


def utcnow() -> datetime:
    """返回 tz-aware UTC 时间；禁止 datetime.now() 的 naive 歧义。"""
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None) -> str | None:
    """序列化为带 Z 的 UTC ISO 字符串；None 原样返回。"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def new_id_str() -> str:
    """字符串形式的 UUIDv7，便于 dataclass 与 JSON 直接传递。"""
    return str(uuid7())


def random_token(nbytes: int = 16) -> str:
    """生成不可预测的令牌（目前供种子/测试补全占位，不用于认证）。"""
    return secrets.token_urlsafe(nbytes)
