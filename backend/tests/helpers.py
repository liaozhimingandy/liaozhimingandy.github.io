"""测试共享辅助：SQLite 内存库装配 + 会话注入 + 种子数据。

所有契约测试统一走 core.database 的内存引擎（与生产 Postgres 同一套
SQLModel/DAL/Service 代码路径），不再使用旧 Memory 仓储。
"""

from __future__ import annotations

import asyncio
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from fastapi.testclient import TestClient

from app.auth import DevHeaderProvider
from app.core import database
from app.core.database import get_session
from app.portal.models import AppCategory, ApplicationCategoryRel, PortalApp
from app.portal.service import PortalService
from main import app

ADMIN_SUB = "admin-sub"
USER_A = "user-a"
USER_B = "user-b"


def admin_headers() -> dict[str, str]:
    return {"X-User-Sub": ADMIN_SUB}


def user_headers(sub: str = USER_A) -> dict[str, str]:
    return {"X-User-Sub": sub}


def use_memory_db() -> None:
    """切换到全新 SQLite 内存引擎并建表（含 article + portal 全部表）。"""
    database.use_memory_engine()
    asyncio.run(database.init_tables())


def dispose_memory_db() -> None:
    asyncio.run(database.dispose_engine())


def run_db(fn: Callable[..., Any], *args: Any) -> Any:
    """在内存库上执行一段 async 种子/查询逻辑（fn(session, *args)）。"""
    async def _inner():
        async with database.session_scope() as session:
            return await fn(session, *args)
    return asyncio.run(_inner)


def seed_portal_fixtures() -> dict[str, str]:
    """门户标准测试数据：分类 all/ai + 四个典型应用；返回 code -> app_id。"""
    async def _inner() -> dict[str, str]:
        async with database.session_scope() as session:
            svc = PortalService(session)
            for cat in (
                AppCategory(code="all", name="全部应用", sort_order=0),
                AppCategory(code="ai", name="AI 工具", sort_order=10),
            ):
                if await svc.categories.get_by_code(cat.code) is None:
                    session.add(cat)
            await session.flush()

            published_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
            fixtures = {
                "PUB": PortalApp(
                    code="PUB", name="公开应用", status="published", visibility="public",
                    launch_url="https://example.com/pub",
                    published_at=published_at, sort_order=10),
                "DRAFT": PortalApp(
                    code="DRAFT", name="草稿应用", status="draft", visibility="public"),
                "PRIVATE": PortalApp(
                    code="PRIVATE", name="私有应用", status="published", visibility="private",
                    launch_url="https://example.com/priv",
                    published_at=published_at),
                "AUTH": PortalApp(
                    code="AUTH", name="需登录应用", status="published", visibility="public",
                    auth_required=True, launch_url="https://example.com/auth",
                    published_at=published_at),
            }
            ids: dict[str, str] = {}
            for code, app_row in fixtures.items():
                session.add(app_row)
                await session.flush()
                ids[code] = str(app_row.id)
                session.add(ApplicationCategoryRel(
                    app_id=app_row.id,
                    category_id=(await svc.categories.get_by_code("all")).id))
            return ids
    return asyncio.run(_inner())


def seed_app(**kwargs) -> str:
    """快速造一个应用（默认 draft），返回 app id。"""
    async def _inner() -> str:
        async with database.session_scope() as session:
            svc = PortalService(session)
            app_row = PortalApp(**kwargs)
            session.add(app_row)
            await session.flush()
            return str(app_row.id)
    return asyncio.run(_inner())


def get_app_id_by_code(code: str) -> str:
    async def _inner() -> str:
        async with database.session_scope() as session:
            svc = PortalService(session)
            app_row = await svc.apps.get_by_code(code)
            assert app_row is not None
            return str(app_row.id)
    return asyncio.run(_inner())


@contextmanager
def patch_env(**values: str | None) -> Iterator[None]:
    """临时改环境变量并 reload Settings；退出恢复。"""
    from app.core.config import reload_settings

    old = {k: os.environ.get(k) for k in values}
    try:
        for k, v in values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        reload_settings()
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        reload_settings()


@contextmanager
def api_client(*, admin_config: str = ADMIN_SUB,
               seed_fixtures: bool = True,
               auth_provider: Any = None) -> Iterator[TestClient]:
    """门户/配置 API 测试客户端：内存库 + 会话依赖覆盖 + dev 鉴权。

    admin_config 为 PORTAL_ADMIN_SUBS 环境值；改变后 reload_settings()
    使 Settings 单例重新读取（生产环境 env 在进程启动前已就绪，无此问题）。
    auth_provider 传入自定义鉴权 provider（如 StubProvider）。
    """
    old_admin = os.environ.get("PORTAL_ADMIN_SUBS")
    os.environ["PORTAL_ADMIN_SUBS"] = admin_config
    from app.core.config import reload_settings
    from app import runtime
    reload_settings()
    use_memory_db()
    try:
        runtime.wire(app)
        app.state.auth_provider = auth_provider or DevHeaderProvider()

        async def _override_session():
            async with database.session_factory()() as session:
                yield session

        app.dependency_overrides[get_session] = _override_session
        if seed_fixtures:
            seed_portal_fixtures()
        client = TestClient(app)  # 不进 lifespan，避免启动 article 调度
        yield client
    finally:
        app.dependency_overrides.pop(get_session, None)
        dispose_memory_db()
        if old_admin is None:
            os.environ.pop("PORTAL_ADMIN_SUBS", None)
        else:
            os.environ["PORTAL_ADMIN_SUBS"] = old_admin
        reload_settings()
