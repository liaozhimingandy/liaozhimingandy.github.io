"""Also Apps 门户领域层：SQLModel 表模型 + 领域错误 + URL 校验。

表模型与线上已迁移的 PG 表（sql/004_apps_portal.sql / 001_tool_configs.sql）
同名列同语义：建表走 SQLModel.metadata.create_all（只建不存在的表），
PG 上 create_all 对已有表是 no-op，两侧结构同源。

约定：
  - 主键 id 用 UUIDv7（Python 侧生成，时间有序；与 PG server_default 双保险）；
  - 时间一律 aware UTC datetime；对外 JSON 序列化为 'Z' 结尾 ISO 字符串；
  - user_sub 是 Logto sub，唯一可信用户标识；任何模型不接受客户端传入的
    user_sub 作为查询/写入条件（由 API 层从 auth provider 注入）；
  - app_type/status/visibility/open_mode 取值由 service 层白名单校验
    （PG 侧还有 CHECK 约束兜底）。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    Integer,
    Text,
    Uuid,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel

from ..portal_ids import uuid7


def utcnow() -> datetime:
    """aware UTC 当前时间（Postgres timestamptz / SQLite 均可写入）。"""
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None) -> str | None:
    """序列化为带 Z 的 UTC ISO 字符串；None 原样返回。"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


# --------------------------------------------------------------------------- #
# 枚举取值（与 SQL CHECK 一致）
# --------------------------------------------------------------------------- #

AppType = Literal["application", "tool", "game", "service"]
OpenMode = Literal["same_tab", "new_tab"]
AppStatus = Literal["draft", "published", "disabled"]
Visibility = Literal["public", "private"]

APP_TYPES: tuple[str, ...] = ("application", "tool", "game", "service")
OPEN_MODES: tuple[str, ...] = ("same_tab", "new_tab")
APP_STATUSES: tuple[str, ...] = ("draft", "published", "disabled")
VISIBILITIES: tuple[str, ...] = ("public", "private")
CATEGORY_STATUSES: tuple[str, ...] = ("enabled", "disabled")


# --------------------------------------------------------------------------- #
# 领域错误（API 层映射为统一错误码）
# --------------------------------------------------------------------------- #

class PortalError(Exception):
    """门户领域错误基类。"""

    code = "PORTAL_ERROR"
    status_code = 400


class NotFoundError(PortalError):
    code = "NOT_FOUND"
    status_code = 404


class ConflictError(PortalError):
    """冲突（编码已存在 / 乐观锁版本不一致）。

    乐观锁冲突时携带 expected/actual 修订号，供 API 层组装 ConflictDetail。
    """

    code = "CONFLICT"
    status_code = 409

    def __init__(self, message: str = "conflict", *,
                 expected: int | None = None, actual: int | None = None) -> None:
        super().__init__(message)
        self.expected = expected
        self.actual = actual


class ForbiddenError(PortalError):
    code = "FORBIDDEN"
    status_code = 403


class ValidationError(PortalError):
    code = "VALIDATION_ERROR"
    status_code = 422


# --------------------------------------------------------------------------- #
# URL 安全校验
# --------------------------------------------------------------------------- #

# 绝对地址：仅 http/https 且必须有主机；禁止 userinfo（防钓鱼伪装）。
_SAFE_URL_RE = re.compile(r"^https?://[^/\s@?#]+(?::\d+)?(?:/[^\s]*)?$", re.IGNORECASE)
# 本站相对路径：以单个 / 开头（// 开头是 protocol-relative 外站地址，拒绝）。
_SAFE_SITE_PATH_RE = re.compile(r"^/(?!/)[^\s\\]*$")


def validate_launch_url(url: str) -> str:
    """校验应用访问地址：空串允许（草稿/未部署）。

    非空接受 http/https 绝对地址或以单个 / 开头的本站相对路径。
    双重防线：SQL CHECK 已做粗校验，这里做严格校验（含 userinfo、控制字符）。
    """
    value = (url or "").strip()
    if not value:
        return ""
    if any(ord(c) < 0x20 for c in value):
        raise ValidationError("launch_url 不允许包含控制字符")
    if _SAFE_SITE_PATH_RE.match(value):
        return value
    if not _SAFE_URL_RE.match(value):
        raise ValidationError("launch_url 必须是合法的 http/https 地址或以 / 开头的本站相对路径")
    parsed = urlparse(value)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc or parsed.username:
        raise ValidationError("launch_url 不允许包含用户凭据或非 http(s) 协议")
    return value


def app_in_public_catalog(status: str, visibility: str) -> bool:
    """是否允许出现在匿名公开目录中：已发布 + public 展示范围。"""
    return status == "published" and visibility == "public"


# --------------------------------------------------------------------------- #
# 表模型
# --------------------------------------------------------------------------- #

def _uuid_pk() -> Any:
    return Field(default_factory=uuid7, sa_column=Column(Uuid(), primary_key=True))


def _tz_column() -> Any:
    return Field(default_factory=utcnow, sa_column=Column(DateTime(timezone=True)))


class PortalApp(SQLModel, table=True):
    """门户应用目录（portal_apps）：展示与导航数据唯一来源，不含业务授权。"""

    __tablename__ = "portal_apps"
    __table_args__ = (UniqueConstraint("code", name="uq_portal_apps_code"),)

    id: UUID = _uuid_pk()
    code: str = Field(max_length=64, index=True)
    name: str = Field(max_length=100)
    subtitle: str = Field(default="", max_length=200)
    description: str = Field(default="", sa_column=Column(Text))
    detail: str = Field(default="", sa_column=Column(Text))
    icon_url: str = Field(default="", max_length=500)
    cover_url: str = Field(default="", max_length=500)
    launch_url: str = Field(default="", max_length=1000)
    app_type: str = Field(default="application", max_length=32)
    open_mode: str = Field(default="new_tab", max_length=20)
    status: str = Field(default="draft", max_length=20, index=True)
    visibility: str = Field(default="public", max_length=20)
    auth_required: bool = Field(default=False)
    is_featured: bool = Field(default=False)
    show_on_home: bool = Field(default=False)
    is_new: bool = Field(default=False)
    is_offline_soon: bool = Field(default=False)
    sort_order: int = Field(default=0)
    published_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_by: str | None = Field(default=None)
    updated_by: str | None = Field(default=None)
    created_at: datetime = _tz_column()
    updated_at: datetime = _tz_column()

    def to_public(self, categories: tuple[str, ...] = ()) -> dict[str, Any]:
        """公开响应形状（与旧 AppRecord.to_public 完全一致）。"""
        return {
            "id": str(self.id),
            "code": self.code,
            "name": self.name,
            "subtitle": self.subtitle,
            "description": self.description,
            "detail": self.detail,
            "icon_url": self.icon_url,
            "cover_url": self.cover_url,
            "launch_url": self.launch_url,
            "app_type": self.app_type,
            "open_mode": self.open_mode,
            "status": self.status,
            "visibility": self.visibility,
            "auth_required": self.auth_required,
            "is_featured": self.is_featured,
            "show_on_home": self.show_on_home,
            "is_new": self.is_new,
            "is_offline_soon": self.is_offline_soon,
            "sort_order": self.sort_order,
            "published_at": iso_utc(self.published_at),
            "categories": list(categories),
            "created_at": iso_utc(self.created_at) or "",
            "updated_at": iso_utc(self.updated_at) or "",
        }


class AppCategory(SQLModel, table=True):
    """应用分类（app_categories）。parent_id 预留二级分类。"""

    __tablename__ = "app_categories"
    __table_args__ = (UniqueConstraint("code", name="uq_app_categories_code"),)

    id: UUID = _uuid_pk()
    code: str = Field(max_length=64, index=True)
    name: str = Field(max_length=100)
    description: str = Field(default="", sa_column=Column(Text))
    icon: str = Field(default="", max_length=200)
    parent_id: UUID | None = Field(default=None, sa_column=Column(Uuid()))
    sort_order: int = Field(default=0)
    status: str = Field(default="enabled", max_length=20)
    created_at: datetime = _tz_column()
    updated_at: datetime = _tz_column()

    def to_public(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "sort_order": self.sort_order,
            "status": self.status,
            "created_at": iso_utc(self.created_at) or "",
            "updated_at": iso_utc(self.updated_at) or "",
        }


class ApplicationCategoryRel(SQLModel, table=True):
    """应用-分类多对多关联（application_categories）。"""

    __tablename__ = "application_categories"

    app_id: UUID = Field(sa_column=Column(Uuid(), primary_key=True))
    category_id: UUID = Field(sa_column=Column(Uuid(), primary_key=True))
    created_at: datetime = _tz_column()


class UserAppFavorite(SQLModel, table=True):
    """用户收藏（user_app_favorites）。user_sub 只由鉴权层注入。"""

    __tablename__ = "user_app_favorites"
    __table_args__ = (UniqueConstraint("user_sub", "app_id", name="uq_user_app_favorites"),)

    id: UUID = _uuid_pk()
    user_sub: str = Field(index=True)
    app_id: UUID = Field(sa_column=Column(Uuid()))
    sort_order: int = Field(default=0)
    created_at: datetime = _tz_column()

    def to_public(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "app_id": str(self.app_id),
            "sort_order": self.sort_order,
            "created_at": iso_utc(self.created_at) or "",
        }


class UserAppRecentVisit(SQLModel, table=True):
    """最近访问（user_app_recent_visits）：每用户每应用一行，重复访问累加。"""

    __tablename__ = "user_app_recent_visits"
    __table_args__ = (
        UniqueConstraint("user_sub", "app_id", name="uq_user_app_recent_visits"),
    )

    id: UUID = _uuid_pk()
    user_sub: str = Field(index=True)
    app_id: UUID = Field(sa_column=Column(Uuid()))
    last_visited_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime(timezone=True)))
    visit_count: int = Field(default=1)
    created_at: datetime = _tz_column()
    updated_at: datetime = _tz_column()

    def to_public(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "app_id": str(self.app_id),
            "last_visited_at": iso_utc(self.last_visited_at) or "",
            "visit_count": self.visit_count,
            "created_at": iso_utc(self.created_at) or "",
            "updated_at": iso_utc(self.updated_at) or "",
        }


class ToolConfig(SQLModel, table=True):
    """公共配置表（tool_configs）：零知识密文 blob，value 后端不解析。"""

    __tablename__ = "tool_configs"
    __table_args__ = (
        UniqueConstraint("user_sub", "tool_id", "key", name="uq_tool_configs"),
    )

    # SQLite 下 BigInteger 主键不自增，用 Integer variant（PG 侧仍是 BIGSERIAL 语义）
    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True),
    )
    user_sub: str = Field(index=True)
    tool_id: str = Field(index=True)
    key: str = Field(index=True)
    value: Any = Field(default=None, sa_column=Column(JSON))
    schema_version: int = Field(default=1)
    updated_by_device: str | None = Field(default=None)
    revision: int = Field(default=1)
    created_at: datetime = _tz_column()
    updated_at: datetime = _tz_column()
    deleted_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
