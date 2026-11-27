"""portal 服务层：业务编排与事务边界。

分层：API 路由（router.py / admin_router.py / configs_router.py）
经 Depends(get_session) 注入本层；数据读写只走 dal（BaseDAO + 各表 DAO）；
DAO 只 flush 不 commit，事务出口统一在本层。

安全契约：
  - user_sub 只由 API 层从鉴权 provider 注入，本层不产生、不猜测身份；
  - 用户私有数据（收藏/最近访问/tool_configs）的每个事务开头注入
    PG RLS GUC（app.user_sub），SQLite（测试）自动跳过；
  - 管理接口的权限判定在 API 层（require_admin），本层不做二次鉴权。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from .dal import AppDAO, CategoryDAO, FavoriteDAO, RecentDAO, ToolConfigDAO
from .models import (
    AppCategory,
    PortalApp,
    PortalError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    app_in_public_catalog,
    validate_launch_url,
    utcnow,
)
from .seed import DEFAULT_APPS, DEFAULT_CATEGORIES


# --------------------------------------------------------------------------- #
# PG RLS：用户私有表事务级隔离（纵深防御，应用层 WHERE 过滤之外的第二道闸）
# --------------------------------------------------------------------------- #

async def apply_user_scope(session: AsyncSession, user_sub: str) -> None:
    """在当前事务内声明 app.user_sub；RLS 据此兜底隔离租户。

    仅 Postgres 生效（SQLite 测试库无 RLS）；GUC 是事务级的，
    事务提交/回滚后自动失效，因此每个用户态服务方法开头都要调用。
    ⚠️ 前提：连接 DSN 必须是非特权应用角色（sql/002_app_role.sql），
    超级用户带 BYPASSRLS 会绕过策略。
    """
    bind = session.get_bind()
    if bind is not None and getattr(bind.dialect, "name", "") == "postgresql":
        await session.execute(
            text("SELECT set_config('app.user_sub', :sub, true)"),
            {"sub": user_sub},
        )


# --------------------------------------------------------------------------- #
# 工具注册表投影（/v1/tools：以 portal_apps 为唯一数据源）
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ToolRecord:
    """一条工具元信息（portal 应用的投影）。不含任何用户数据。"""

    tool_id: str
    name: str
    icon: str
    description: str
    enabled: bool
    sort_order: int
    default_max_keys: int | None
    default_max_value_bytes: int | None
    created_at: str
    updated_at: str

    def to_public(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "icon": self.icon,
            "description": self.description,
            "enabled": self.enabled,
            "sort_order": self.sort_order,
            "default_max_keys": self.default_max_keys,
            "default_max_value_bytes": self.default_max_value_bytes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _to_tool_record(app: PortalApp, categories: tuple[str, ...] = ()) -> ToolRecord:
    return ToolRecord(
        tool_id=app.code.lower(),
        name=app.name,
        icon=app.icon_url or "",
        description=app.subtitle or app.description or "",
        enabled=app.status == "published",
        sort_order=app.sort_order,
        default_max_keys=None,
        default_max_value_bytes=None,
        created_at=app.to_public()["created_at"],
        updated_at=app.to_public()["updated_at"],
    )


class QuotaExceededError(PortalError):
    """单工具配置数量超过配额。"""

    code = "QUOTA_EXCEEDED"
    status_code = 409


# --------------------------------------------------------------------------- #
# Portal 服务
# --------------------------------------------------------------------------- #

class PortalService:
    """门户业务服务：公开目录 / 用户收藏访问 / 管理 CRUD / 工具注册表。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.apps = AppDAO(session)
        self.categories = CategoryDAO(session)
        self.favorites = FavoriteDAO(session)
        self.recents = RecentDAO(session)
        self.configs = ToolConfigDAO(session)

    # ---------------------------------------------------------------- 装配
    async def _decorate(self, app: PortalApp,
                        grouped: dict[UUID, tuple[str, ...]] | None = None
                        ) -> dict[str, Any]:
        """App 行 -> 公开 JSON（分类 code 装配进来）。"""
        if grouped is None:
            grouped = await self.apps.categories_of([app.id])
        return app.to_public(grouped.get(app.id, ()))

    async def _decorate_many(self, apps: list[PortalApp]) -> list[dict[str, Any]]:
        grouped = await self.apps.categories_of([a.id for a in apps])
        return [a.to_public(grouped.get(a.id, ())) for a in apps]

    async def decorate_app(self, app: PortalApp) -> dict[str, Any]:
        """单个 App 行 -> 公开 JSON（供路由层装配已取出的实体）。"""
        return await self._decorate(app)

    # ---------------------------------------------------------------- 公开目录
    async def list_apps_public(self, *, category: str | None = None,
                               keyword: str = "", featured_only: bool = False,
                               home_only: bool = False, page: int = 1,
                               page_size: int = 20) -> dict[str, Any]:
        rows = await self.apps.search(
            status="published", category=category, keyword=keyword,
            featured_only=featured_only, home_only=home_only,
            limit=page_size, offset=(page - 1) * page_size,
        )
        total = await self.apps.count_apps(
            status="published", category=category, keyword=keyword,
            featured_only=featured_only, home_only=home_only,
        )
        return {
            "items": await self._decorate_many(rows),
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def list_featured(self) -> list[dict[str, Any]]:
        rows = await self.apps.search(
            status="published", featured_only=True)
        return await self._decorate_many(rows)

    async def search_apps(self, q: str = "", category: str | None = None
                          ) -> list[dict[str, Any]]:
        rows = await self.apps.search(
            status="published", keyword=q, category=category)
        return await self._decorate_many(rows)

    async def get_app_by_code(self, code: str) -> PortalApp | None:
        return await self.apps.get_by_code(code)

    async def get_app_by_id(self, app_id: str) -> PortalApp | None:
        return await self.apps.get_by_id(app_id)

    async def get_app_public(self, code: str) -> dict[str, Any]:
        app = await self.apps.get_by_code(code)
        if app is None:
            raise NotFoundError("应用不存在")
        return await self._decorate(app)

    async def get_app_detail(self, code: str, user_sub: str | None) -> dict[str, Any]:
        """公开详情 + favorited 标记（已登录时）。

        未发布/private 一律 NotFoundError（不泄露存在性），由路由映射为
        APP_NOT_FOUND 错误码。
        """
        app = await self.apps.get_by_code(code)
        if not app or app.status != "published" or app.visibility == "private":
            raise NotFoundError("应用不存在或未发布")
        result = await self._decorate(app)
        result["favorited"] = False
        if user_sub:
            await apply_user_scope(self.session, user_sub)
            favs = await self.favorites.list_favorites(user_sub)
            result["favorited"] = any(str(f.app_id) == str(app.id) for f in favs)
        return result

    async def list_categories(self, *, enabled_only: bool = True
                              ) -> list[dict[str, Any]]:
        rows = await self.categories.list_categories(enabled_only=enabled_only)
        return [c.to_public() for c in rows]

    # ---------------------------------------------------------------- 应用启动校验
    async def check_launch(self, code: str, principal_sub: str | None
                           ) -> dict[str, Any]:
        """启动前服务端二次校验：发布状态、登录要求、可见范围、地址安全。"""
        app = await self.apps.get_by_code(code)
        if not app or app.status != "published":
            raise NotFoundError("应用不存在或未发布")
        if app.visibility == "private":
            raise ForbiddenError("该应用需要授权后才能访问")
        app_public = await self._decorate(app)
        if app.auth_required and principal_sub is None:
            return {
                "allowed": False,
                "reason": "LOGIN_REQUIRED",
                "message": "请先登录 Also Account 后再访问该应用",
                "app": app_public,
            }
        if not app.launch_url:
            return {
                "allowed": False,
                "reason": "NOT_DEPLOYED",
                "message": "该应用尚未开放访问",
                "app": app_public,
            }
        validate_launch_url(app.launch_url)
        return {
            "allowed": True,
            "reason": None,
            "message": "",
            "app": app_public,
            "url": app.launch_url,
            "open_mode": app.open_mode,
        }

    # ---------------------------------------------------------------- 用户收藏
    async def my_favorites(self, user_sub: str) -> list[dict[str, Any]]:
        await apply_user_scope(self.session, user_sub)
        favs = await self.favorites.list_favorites(user_sub)
        grouped = await self.apps.categories_of([f.app_id for f in favs])
        apps: list[dict[str, Any]] = []
        for fav in favs:
            app = await self.apps.get_by_id(fav.app_id)
            if app and app_in_public_catalog(app.status, app.visibility):
                data = app.to_public(grouped.get(fav.app_id, ()))
                data["sort_order"] = fav.sort_order
                apps.append(data)
        return apps

    async def add_favorite(self, user_sub: str, app_id: str) -> dict[str, Any]:
        app = await self.apps.get_by_id(app_id)
        if not app or not app_in_public_catalog(app.status, app.visibility):
            raise NotFoundError("应用不存在或未发布")
        await apply_user_scope(self.session, user_sub)
        try:
            fav = await self.favorites.add_favorite(user_sub, app.id)
        except ValueError as exc:
            raise ConflictError(str(exc)) from None
        await self.session.commit()
        return fav.to_public()

    async def remove_favorite(self, user_sub: str, app_id: str) -> None:
        await apply_user_scope(self.session, user_sub)
        removed = await self.favorites.remove_favorite(user_sub, app_id)
        if not removed:
            raise NotFoundError("收藏记录不存在")
        await self.session.commit()

    async def reorder_favorites(self, user_sub: str, app_ids: list[str]) -> list[dict[str, Any]]:
        await apply_user_scope(self.session, user_sub)
        await self.favorites.reorder(user_sub, app_ids)
        await self.session.commit()
        favs = await self.favorites.list_favorites(user_sub)
        return [f.to_public() for f in favs]

    # ---------------------------------------------------------------- 最近访问
    async def my_recent(self, user_sub: str, limit: int = 10) -> list[dict[str, Any]]:
        await apply_user_scope(self.session, user_sub)
        visits = await self.recents.list_recent(user_sub, limit=limit)
        items: list[dict[str, Any]] = []
        for visit in visits:
            app = await self.apps.get_by_id(visit.app_id)
            if app and app_in_public_catalog(app.status, app.visibility):
                data = app.to_public()
                data["last_visited_at"] = visit.to_public()["last_visited_at"]
                data["visit_count"] = visit.visit_count
                items.append(data)
        return items

    async def record_visit(self, user_sub: str, app_id: str) -> dict[str, Any]:
        app = await self.apps.get_by_id(app_id)
        if not app or not app_in_public_catalog(app.status, app.visibility):
            raise NotFoundError("应用不存在或未发布")
        await apply_user_scope(self.session, user_sub)
        visit = await self.recents.record_visit(user_sub, app.id)
        await self.session.commit()
        return visit.to_public()

    # ---------------------------------------------------------------- 管理端：应用
    async def admin_list_apps(self, *, status: str | None = None,
                              app_type: str | None = None,
                              category: str | None = None,
                              keyword: str = "") -> list[dict[str, Any]]:
        rows = await self.apps.search(
            status=status, category=category, keyword=keyword,
            include_private=True)
        if app_type:
            rows = [a for a in rows if a.app_type == app_type]
        return await self._decorate_many(rows)

    async def admin_create_app(self, payload: dict[str, Any],
                               categories: tuple[str, ...],
                               admin_sub: str) -> dict[str, Any]:
        code = payload["code"]
        if await self.apps.code_exists(code):
            raise ConflictError("应用编码已存在")
        app = PortalApp(
            code=code,
            name=payload.get("name") or code,
            subtitle=payload.get("subtitle", ""),
            description=payload.get("description", ""),
            detail=payload.get("detail", ""),
            icon_url=payload.get("icon_url", ""),
            cover_url=payload.get("cover_url", ""),
            launch_url=validate_launch_url(str(payload.get("launch_url", ""))),
            app_type=payload.get("app_type", "application"),
            open_mode=payload.get("open_mode", "new_tab"),
            status=payload.get("status", "draft"),
            visibility=payload.get("visibility", "public"),
            auth_required=bool(payload.get("auth_required", False)),
            is_featured=bool(payload.get("is_featured", False)),
            show_on_home=bool(payload.get("show_on_home", False)),
            is_new=bool(payload.get("is_new", False)),
            is_offline_soon=bool(payload.get("is_offline_soon", False)),
            sort_order=int(payload.get("sort_order", 0)),
            created_by=admin_sub,
            updated_by=admin_sub,
        )
        if app.status == "published" and app.published_at is None:
            app.published_at = utcnow()
        await self.apps.create(app)
        await self.apps.set_categories(app.id, categories)
        await self.session.commit()
        return await self._decorate(app)

    async def admin_update_app(self, app_id: str, changes: dict[str, Any],
                               categories: tuple[str, ...] | None = None
                               ) -> dict[str, Any]:
        app = await self.apps.get_by_id(app_id)
        if app is None:
            raise NotFoundError("应用不存在")
        if "launch_url" in changes:
            changes["launch_url"] = validate_launch_url(str(changes["launch_url"]))
        allowed = {
            "name", "subtitle", "description", "detail", "icon_url", "cover_url",
            "launch_url", "app_type", "open_mode", "status", "visibility",
            "auth_required", "is_featured", "show_on_home", "is_new",
            "is_offline_soon", "sort_order", "updated_by",
        }
        for key, value in changes.items():
            if key in allowed:
                setattr(app, key, value)
        if changes.get("status") == "published":
            if app.published_at is None:
                app.published_at = utcnow()
        elif "status" in changes:
            app.published_at = None
        app.updated_at = utcnow()
        await self.session.flush()
        if categories is not None:
            await self.apps.set_categories(app.id, categories)
        await self.session.commit()
        return await self._decorate(app)

    async def admin_delete_app(self, app_id: str) -> None:
        deleted = await self.apps.delete_cascade(app_id)
        if not deleted:
            raise NotFoundError("应用不存在")
        await self.session.commit()

    async def admin_set_homepage(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        updated: list[dict[str, Any]] = []
        for item in items:
            app = await self.apps.get_by_id(item["id"])
            if app is None:
                raise NotFoundError("应用不存在")
            for key in ("show_on_home", "is_featured", "sort_order"):
                if key in item:
                    setattr(app, key, item[key])
            app.updated_at = utcnow()
            await self.session.flush()
            updated.append(await self._decorate(app))
        await self.session.commit()
        return updated

    # ---------------------------------------------------------------- 管理端：分类
    async def admin_create_category(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            cat = await self.categories.create(AppCategory(
                code=payload["code"],
                name=payload["name"],
                description=payload.get("description", ""),
                icon=payload.get("icon", ""),
                parent_id=payload.get("parent_id"),
                sort_order=int(payload.get("sort_order", 0)),
                status=payload.get("status", "enabled"),
            ))
        except ValueError as exc:
            raise ConflictError(str(exc)) from None
        await self.session.commit()
        return cat.to_public()

    async def admin_update_category(self, category_id: str,
                                    changes: dict[str, Any]) -> dict[str, Any]:
        cat = await self.categories.get_by_id(category_id)
        if cat is None:
            raise NotFoundError("分类不存在")
        for key, value in changes.items():
            if key == "parent_id" and value:
                value = UUID(str(value))
            setattr(cat, key, value)
        cat.updated_at = utcnow()
        await self.session.flush()
        await self.session.commit()
        return cat.to_public()

    async def admin_delete_category(self, category_id: str) -> None:
        deleted = await self.categories.delete_cascade(category_id)
        if not deleted:
            raise NotFoundError("分类不存在")
        await self.session.commit()

    # ---------------------------------------------------------------- 管理端：访问统计
    async def admin_visits(self, limit: int = 50) -> list[dict[str, Any]]:
        """访问统计（应用维度聚合，不返回 user_sub）。当前返回空列表。"""
        return []

    # ---------------------------------------------------------------- 工具注册表
    async def list_tools(self, *, enabled_only: bool = True) -> list[ToolRecord]:
        apps = await self.apps.search(
            status="published" if enabled_only else None, include_private=True)
        rows = [_to_tool_record(a) for a in apps]
        return sorted(rows, key=lambda t: (t.sort_order, t.tool_id))

    async def get_tool(self, tool_id: str) -> ToolRecord | None:
        app = await self.apps.get_by_code(tool_id)
        return _to_tool_record(app) if app is not None else None

    async def exists_enabled(self, tool_id: str) -> bool:
        app = await self.apps.get_by_code(tool_id)
        return app is not None and app.status == "published"

    async def resolve_quota(self, tool_id: str, *, max_keys: int,
                            max_bytes: int) -> tuple[int, int]:
        """最终配额：工具注册表的非 NULL 覆盖值优先，否则全局默认。"""
        tool = await self.get_tool(tool_id)
        if tool is not None:
            if tool.default_max_keys is not None and tool.default_max_keys > 0:
                max_keys = tool.default_max_keys
            if tool.default_max_value_bytes is not None and tool.default_max_value_bytes > 0:
                max_bytes = tool.default_max_value_bytes
        return max_keys, max_bytes

    # ---------------------------------------------------------------- 种子
    async def seed_if_empty(self) -> None:
        """幂等种子：categories / apps 按 code 缺席才插入（SQLite 空库/内存模式用）。"""
        for cat in DEFAULT_CATEGORIES:
            if await self.categories.get_by_code(cat.code) is None:
                self.session.add(cat)
        for app, codes in DEFAULT_APPS:
            if await self.apps.get_by_code(app.code) is None:
                self.session.add(app)
                await self.session.flush()
                await self.apps.set_categories(app.id, codes)
        await self.session.commit()


# --------------------------------------------------------------------------- #
# 公共配置（零知识密文同步）服务
# --------------------------------------------------------------------------- #

class ConfigService:
    """tool_configs 业务服务：CAS 读写 + 配额判定。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.dao = ToolConfigDAO(session)

    async def list(self, user_sub: str, tool_id: str,
                   *, include_deleted: bool = False) -> list[dict[str, Any]]:
        await apply_user_scope(self.session, user_sub)
        rows = await self.dao.list(user_sub, tool_id, include_deleted=include_deleted)
        return [self.dao.to_public(r) for r in rows]

    async def get(self, user_sub: str, tool_id: str, key: str) -> dict[str, Any]:
        await apply_user_scope(self.session, user_sub)
        rec = await self.dao.get(user_sub, tool_id, key)
        if rec is None:
            raise NotFoundError(f"{tool_id}/{key} not found")
        return self.dao.to_public(rec)

    async def put(self, user_sub: str, tool_id: str, key: str, value: Any,
                  *, expected_revision: int | None, schema_version: int = 1,
                  updated_by_device: str | None = None,
                  max_keys: int | None = None) -> dict[str, Any]:
        """UPSERT；首次创建（expected_revision == 0）先查配额。"""
        await apply_user_scope(self.session, user_sub)
        if expected_revision == 0 and max_keys is not None:
            existing = await self.dao.count_keys(user_sub, tool_id)
            already = await self.dao.get_any(user_sub, tool_id, key)
            if already is None and existing >= max_keys:
                raise QuotaExceededError("该工具下配置数量已达上限")
        try:
            rec = await self.dao.put(
                user_sub, tool_id, key, value,
                expected_revision=expected_revision,
                schema_version=schema_version,
                updated_by_device=updated_by_device,
            )
        except ValueError as exc:
            raise ConflictError(str(exc)) from None
        await self.session.commit()
        return self.dao.to_public(rec)

    async def delete(self, user_sub: str, tool_id: str, key: str,
                     expected_revision: int) -> dict[str, Any]:
        await apply_user_scope(self.session, user_sub)
        rec = await self.dao.soft_delete(user_sub, tool_id, key, expected_revision)
        await self.session.commit()
        return self.dao.to_public(rec)
