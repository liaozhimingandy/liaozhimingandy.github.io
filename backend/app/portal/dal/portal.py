"""portal 各表 DAO：目录/分类/收藏/最近访问。

约定（与 article DAL 一致）：
  - 所有写操作只 flush 不 commit，事务边界在 service / session_scope；
  - 跨方言兼容：Postgres（生产）与 SQLite 内存库（测试）都能执行，
    关键字搜索用 lower+like（不用 ILIKE），关联过滤用子查询（不用 JSONB 函数）；
  - 唯一约束冲突用 SAVEPOINT（begin_nested）捕获，不影响同一会话其它写入；
  - user_sub 隔离：应用层 WHERE 过滤 + PG 侧 RLS 兜底（service 层统一注入 GUC）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, or_, update
from sqlmodel import select
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.dal_base import BaseDAO
from ..models import (
    AppCategory,
    ApplicationCategoryRel,
    PortalApp,
    UserAppFavorite,
    UserAppRecentVisit,
    utcnow,
)


def _as_uuid(value: Any) -> Any:
    """路径参数里的字符串 id 转成 UUID 对象；UUID 原样返回。"""
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return value
    return value


# --------------------------------------------------------------------------- #
# 应用目录
# --------------------------------------------------------------------------- #

class AppDAO(BaseDAO[PortalApp]):
    model = PortalApp

    def _base_stmt(self, *, status: str | None, category: str | None,
                   keyword: str, featured_only: bool, home_only: bool,
                   include_private: bool):
        stmt = select(PortalApp)
        if status:
            stmt = stmt.where(PortalApp.status == status)
        if not include_private:
            stmt = stmt.where(PortalApp.visibility == "public")
        if featured_only:
            stmt = stmt.where(PortalApp.is_featured.is_(True))
        if home_only:
            stmt = stmt.where(PortalApp.show_on_home.is_(True))
        if category and category != "all":
            stmt = stmt.where(PortalApp.id.in_(
                select(ApplicationCategoryRel.app_id)
                .join(AppCategory, AppCategory.id == ApplicationCategoryRel.category_id)
                .where(AppCategory.code == category)
            ))
        keyword = keyword.strip().lower()
        if keyword:
            needle = f"%{keyword}%"
            stmt = stmt.where(or_(
                func.lower(PortalApp.code).like(needle),
                func.lower(PortalApp.name).like(needle),
                func.lower(PortalApp.subtitle).like(needle),
                func.lower(PortalApp.description).like(needle),
            ))
        return stmt

    async def search(self, *, status: str | None = None, category: str | None = None,
                     keyword: str = "", featured_only: bool = False,
                     home_only: bool = False, include_private: bool = False,
                     limit: int | None = None, offset: int = 0) -> list[PortalApp]:
        stmt = self._base_stmt(
            status=status, category=category, keyword=keyword,
            featured_only=featured_only, home_only=home_only,
            include_private=include_private,
        ).order_by(PortalApp.sort_order, PortalApp.code)
        if limit is not None:
            stmt = stmt.limit(max(int(limit), 0)).offset(max(int(offset), 0))
        else:
            stmt = stmt.offset(max(int(offset), 0))
        return list((await self._execute(stmt, "search")).all())

    async def count_apps(self, *, status: str | None = None, category: str | None = None,
                         keyword: str = "", featured_only: bool = False,
                         home_only: bool = False, include_private: bool = False) -> int:
        stmt = self._base_stmt(
            status=status, category=category, keyword=keyword,
            featured_only=featured_only, home_only=home_only,
            include_private=include_private,
        )
        result = await self._execute(
            select(func.count()).select_from(stmt.subquery()), "count_apps")
        return int(result.one())

    async def get_by_code(self, code: str) -> PortalApp | None:
        result = await self._execute(
            select(PortalApp).where(PortalApp.code == code.upper()).limit(1),
            "get_by_code")
        return result.first()

    async def get_by_id(self, app_id: str | UUID) -> PortalApp | None:
        result = await self._execute(
            select(PortalApp).where(PortalApp.id == _as_uuid(app_id)).limit(1),
            "get_by_id")
        return result.first()

    async def code_exists(self, code: str) -> bool:
        return await self.exists(code=code.upper())

    async def set_categories(self, app_id: str | UUID,
                             codes: tuple[str, ...]) -> dict[str, UUID]:
        """重绑应用分类：清空旧关联，按 code 建新关联；返回 code->category_id。"""
        await self.exec_write(
            delete(ApplicationCategoryRel).where(
                ApplicationCategoryRel.app_id == app_id), "set_categories.clear")
        code_to_id: dict[str, UUID] = {}
        for code in dict.fromkeys(codes):
            cat = await CategoryDAO(self.session).get_by_code(code)
            if cat is not None:
                code_to_id[cat.code] = cat.id
                self.session.add(ApplicationCategoryRel(
                    app_id=app_id, category_id=cat.id))
        await self.session.flush()
        return code_to_id

    async def categories_of(self, app_ids: list[UUID]) -> dict[UUID, tuple[str, ...]]:
        """批量取应用分类 code（装配 to_public 用）；一次查询防 N+1。"""
        if not app_ids:
            return {}
        stmt = (
            select(ApplicationCategoryRel.app_id, AppCategory.code)
            .join(AppCategory, AppCategory.id == ApplicationCategoryRel.category_id)
            .where(ApplicationCategoryRel.app_id.in_(app_ids))
            .order_by(AppCategory.sort_order)
        )
        rows = (await self._execute(stmt, "categories_of")).all()
        grouped: dict[UUID, list[str]] = {}
        for app_id, code in rows:
            grouped.setdefault(app_id, []).append(str(code))
        return {app_id: tuple(codes) for app_id, codes in grouped.items()}

    async def delete_cascade(self, app_id: str | UUID) -> bool:
        """删除应用及其收藏/访问/分类关联（PG 有 FK CASCADE，这里显式删以兼容 SQLite）。"""
        rid = _as_uuid(app_id)
        for dao_stmt in (
            delete(UserAppFavorite).where(UserAppFavorite.app_id == rid),
            delete(UserAppRecentVisit).where(UserAppRecentVisit.app_id == rid),
            delete(ApplicationCategoryRel).where(ApplicationCategoryRel.app_id == rid),
        ):
            await self.exec_write(dao_stmt, "delete_cascade.rel")
        result = await self.exec_write(
            delete(PortalApp).where(PortalApp.id == rid), "delete_cascade.app")
        return bool(result.rowcount)


# --------------------------------------------------------------------------- #
# 分类
# --------------------------------------------------------------------------- #

class CategoryDAO(BaseDAO[AppCategory]):
    model = AppCategory

    async def list_categories(self, *, enabled_only: bool = True) -> list[AppCategory]:
        stmt = select(AppCategory).order_by(AppCategory.sort_order, AppCategory.code)
        if enabled_only:
            stmt = stmt.where(AppCategory.status == "enabled")
        return list((await self._execute(stmt, "list_categories")).all())

    async def get_by_code(self, code: str) -> AppCategory | None:
        result = await self._execute(
            select(AppCategory).where(AppCategory.code == code).limit(1),
            "get_by_code")
        return result.first()

    async def get_by_id(self, category_id: str | UUID) -> AppCategory | None:
        result = await self._execute(
            select(AppCategory).where(AppCategory.id == _as_uuid(category_id)).limit(1),
            "get_by_id")
        return result.first()

    async def create(self, obj: AppCategory) -> AppCategory:
        self.session.add(obj)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError:
            raise ValueError("分类编码已存在") from None
        await self.session.refresh(obj)
        return obj

    async def delete_cascade(self, category_id: str | UUID) -> bool:
        """删除分类：清关联、把子分类的 parent_id 置空（PG FK 兜底，SQLite 显式删）。"""
        rid = _as_uuid(category_id)
        await self.exec_write(
            delete(ApplicationCategoryRel).where(
                ApplicationCategoryRel.category_id == rid),
            "delete_cascade.rel")
        await self.exec_write(
            update(AppCategory).where(AppCategory.parent_id == rid)
            .values(parent_id=None),
            "delete_cascade.reparent")
        result = await self.exec_write(
            delete(AppCategory).where(AppCategory.id == rid),
            "delete_cascade.cat")
        return bool(result.rowcount)


# --------------------------------------------------------------------------- #
# 用户收藏
# --------------------------------------------------------------------------- #

class FavoriteDAO(BaseDAO[UserAppFavorite]):
    model = UserAppFavorite

    async def list_favorites(self, user_sub: str) -> list[UserAppFavorite]:
        stmt = (
            select(UserAppFavorite)
            .where(UserAppFavorite.user_sub == user_sub)
            .order_by(UserAppFavorite.sort_order, UserAppFavorite.created_at)
        )
        return list((await self._execute(stmt, "list_favorites")).all())

    async def add_favorite(self, user_sub: str, app_id: UUID,
                           sort_order: int = 0) -> UserAppFavorite:
        fav = UserAppFavorite(user_sub=user_sub, app_id=app_id, sort_order=sort_order)
        self.session.add(fav)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError:
            raise ValueError("已收藏该应用") from None
        await self.session.refresh(fav)
        return fav

    async def remove_favorite(self, user_sub: str, app_id: UUID | str) -> bool:
        result = await self.exec_write(
            delete(UserAppFavorite)
            .where(UserAppFavorite.user_sub == user_sub,
                   UserAppFavorite.app_id == _as_uuid(app_id)),
            "remove_favorite")
        return bool(result.rowcount)

    async def reorder(self, user_sub: str, app_ids: list[str]) -> int:
        updated = 0
        for order, app_id in enumerate(app_ids):
            result = await self.exec_write(
                update(UserAppFavorite)
                .where(UserAppFavorite.user_sub == user_sub,
                       UserAppFavorite.app_id == _as_uuid(app_id))
                .values(sort_order=order),
                "reorder")
            updated += int(result.rowcount or 0)
        return updated


# --------------------------------------------------------------------------- #
# 最近访问
# --------------------------------------------------------------------------- #

class RecentDAO(BaseDAO[UserAppRecentVisit]):
    model = UserAppRecentVisit

    async def list_recent(self, user_sub: str, limit: int = 10) -> list[UserAppRecentVisit]:
        stmt = (
            select(UserAppRecentVisit)
            .where(UserAppRecentVisit.user_sub == user_sub)
            .order_by(UserAppRecentVisit.last_visited_at.desc())
            .limit(max(1, min(int(limit), 100)))
        )
        return list((await self._execute(stmt, "list_recent")).all())

    async def record_visit(self, user_sub: str, app_id: UUID) -> UserAppRecentVisit:
        """访问计数 +1；不存在则建行。并发首访用 SAVEPOINT 兜底重读。"""
        existing = await self.get_one(user_sub=user_sub, app_id=app_id)
        if existing is not None:
            existing.visit_count += 1
            existing.last_visited_at = utcnow()
            existing.updated_at = utcnow()
            await self.session.flush()
            return existing
        rec = UserAppRecentVisit(user_sub=user_sub, app_id=app_id)
        self.session.add(rec)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError:
            row = await self.get_one(user_sub=user_sub, app_id=app_id)
            if row is None:
                raise
            row.visit_count += 1
            row.last_visited_at = utcnow()
            row.updated_at = utcnow()
            await self.session.flush()
            return row
        await self.session.refresh(rec)
        return rec
