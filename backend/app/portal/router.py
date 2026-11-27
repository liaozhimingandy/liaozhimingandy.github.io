"""Also Apps 门户 API（统一 /v1 前缀）。

公开目录：
  GET    /v1/portal/apps                 应用列表（分类/搜索/推荐/首页/分页）
  GET    /v1/portal/apps/featured        推荐应用
  GET    /v1/portal/apps/search          搜索（与 apps?keyword= 等价，语义化别名）
  GET    /v1/portal/apps/{code}          应用详情
  GET    /v1/portal/categories           分类列表

用户功能（身份只来自鉴权 provider）：
  GET    /v1/portal/me/capabilities     当前身份的门户能力
  GET    /v1/portal/me/favorites
  POST   /v1/portal/me/favorites/{app_id}
  DELETE /v1/portal/me/favorites/{app_id}
  PUT    /v1/portal/me/favorites/order
  GET    /v1/portal/me/recent
  POST   /v1/portal/me/recent/{app_id}

启动校验（服务端二次判定）：
  POST   /v1/portal/apps/{code}/launch

分层：路由只做参数校验、身份注入与形状映射；业务在 portal/service.py；
数据读写经 Depends(get_session) -> PortalService -> DAO。管理接口见 admin_router.py。

由 app.portal 包在上一级统一导出（from app.portal import router）。

安全契约：
  1. user_sub 只来自鉴权 provider，path/query/body 的用户标识一律忽略。
  2. 公开接口只返回 published + public 的应用。
  3. 管理接口按 PORTAL_ADMIN_SUBS 白名单校验；空白名单 fail-closed。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..auth import AuthProvider, Principal, UnauthorizedError
from ..core.database import get_session
from .models import PortalError
from .service import PortalService
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter()


# --------------------------------------------------------------------------- # 依赖与公共辅助
def _api_error(status: int, code: str, message: str, **extra: Any) -> HTTPException:
    detail: dict[str, Any] = {"error": code, "message": message}
    detail.update(extra)
    return HTTPException(status_code=status, detail=detail)


def get_auth_provider(request: Request) -> AuthProvider:
    """鉴权 provider（runtime.wire 在 lifespan 装配到 app.state）。"""
    return request.app.state.auth_provider


def optional_principal(request: Request) -> Principal | None:
    """可选身份：公开接口允许匿名，带合法令牌时拿到 sub 用于私有应用过滤。"""
    provider: AuthProvider = request.app.state.auth_provider
    headers = {k: v for k, v in request.headers.items()}
    try:
        return provider.authenticate(headers=headers)
    except UnauthorizedError:
        return None


def require_principal(request: Request) -> Principal:
    """强制身份：用户态接口必须登录。"""
    provider: AuthProvider = request.app.state.auth_provider
    headers = {k: v for k, v in request.headers.items()}
    try:
        return provider.authenticate(headers=headers)
    except UnauthorizedError as exc:
        raise _api_error(401, exc.code, str(exc)) from None


def require_admin(principal: Principal = Depends(require_principal)) -> Principal:
    """管理员校验：白名单为空时 fail-closed，绝不裸奔。"""
    from ..core.config import get_settings

    admins = get_settings().portal_admin_sub_set
    if not admins or principal.sub not in admins:
        raise _api_error(403, "FORBIDDEN", "需要管理员权限")
    return principal


async def get_portal_service(
    session: AsyncSession = Depends(get_session),
) -> PortalService:
    """DI 链：请求级会话 -> 门户服务对象。"""
    return PortalService(session)


def _handle_domain_error(exc: Exception) -> None:
    if isinstance(exc, PortalError):
        raise _api_error(exc.status_code, exc.code, str(exc)) from None
    raise exc


# --------------------------------------------------------------------------- # 公开目录
@router.get("/v1/portal/apps", tags=["portal-public"])
async def list_apps(
    category: str = Query(default="", description="分类 code；all 表示全部"),
    keyword: str = Query(default="", max_length=100, description="名称/副标题/简介/编码搜索"),
    featured: bool = Query(default=False, description="仅推荐应用"),
    home: bool = Query(default=False, description="仅首页展示应用"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    principal: Principal | None = Depends(optional_principal),
    svc: PortalService = Depends(get_portal_service),
) -> dict[str, Any]:
    """匿名可读的公开应用目录；query 条件可由前端保留在 URL 中。"""
    try:
        return await svc.list_apps_public(
            category=category or None, keyword=keyword,
            featured_only=featured, home_only=home,
            page=page, page_size=page_size,
        )
    except PortalError as exc:
        _handle_domain_error(exc)


@router.get("/v1/portal/apps/featured", tags=["portal-public"])
async def featured_apps(
    svc: PortalService = Depends(get_portal_service),
) -> dict[str, Any]:
    rows = await svc.list_featured()
    return {"items": rows, "total": len(rows)}


@router.get("/v1/portal/apps/search", tags=["portal-public"])
async def search_apps(
    q: str = Query(default="", max_length=100),
    category: str = Query(default=""),
    svc: PortalService = Depends(get_portal_service),
) -> dict[str, Any]:
    rows = await svc.search_apps(q, category=category or None)
    return {"items": rows, "total": len(rows)}


@router.get("/v1/portal/apps/{code}", tags=["portal-public"])
async def app_detail(
    code: str,
    principal: Principal | None = Depends(optional_principal),
    svc: PortalService = Depends(get_portal_service),
) -> dict[str, Any]:
    """应用详情。private 应用对匿名/未授权者返回 404（不泄露存在性）。"""
    try:
        return await svc.get_app_detail(code, principal.sub if principal else None)
    except PortalError as exc:
        raise _api_error(404, "APP_NOT_FOUND", str(exc)) from None


@router.get("/v1/portal/categories", tags=["portal-public"])
async def list_categories(
    svc: PortalService = Depends(get_portal_service),
) -> dict[str, Any]:
    rows = await svc.list_categories(enabled_only=True)
    return {"items": rows, "total": len(rows)}


# --------------------------------------------------------------------------- # 应用启动校验
@router.post("/v1/portal/apps/{code}/launch", tags=["portal-user"])
async def check_launch(
    code: str,
    principal: Principal | None = Depends(optional_principal),
    svc: PortalService = Depends(get_portal_service),
) -> dict[str, Any]:
    """启动前服务端二次校验：发布状态、登录要求、可见范围、地址安全。"""
    try:
        return await svc.check_launch(code, principal.sub if principal else None)
    except PortalError as exc:
        _handle_domain_error(exc)


# --------------------------------------------------------------------------- # 当前用户能力
@router.get("/v1/portal/me/capabilities", tags=["portal-user"])
async def my_capabilities(
    principal: Principal | None = Depends(optional_principal),
) -> dict[str, Any]:
    """返回「我自己」的门户能力，匿名也正常返回。"""
    from ..core.config import get_settings

    admins = get_settings().portal_admin_sub_set
    is_admin = bool(principal and admins and principal.sub in admins)
    return {
        "authenticated": principal is not None,
        "is_admin": is_admin,
        "can_manage_apps": is_admin,
    }


# --------------------------------------------------------------------------- # 用户收藏
@router.get("/v1/portal/me/favorites", tags=["portal-user"])
async def my_favorites(
    principal: Principal = Depends(require_principal),
    svc: PortalService = Depends(get_portal_service),
) -> dict[str, Any]:
    apps = await svc.my_favorites(principal.sub)
    return {"items": apps, "total": len(apps)}


@router.post("/v1/portal/me/favorites/{app_id}", tags=["portal-user"])
async def add_favorite(
    app_id: str,
    principal: Principal = Depends(require_principal),
    svc: PortalService = Depends(get_portal_service),
) -> dict[str, Any]:
    try:
        favorite = await svc.add_favorite(principal.sub, app_id)
    except PortalError as exc:
        _handle_domain_error(exc)
    return {"ok": True, "favorite": favorite}


@router.delete("/v1/portal/me/favorites/{app_id}", tags=["portal-user"])
async def remove_favorite(
    app_id: str,
    principal: Principal = Depends(require_principal),
    svc: PortalService = Depends(get_portal_service),
) -> dict[str, Any]:
    try:
        await svc.remove_favorite(principal.sub, app_id)
    except PortalError as exc:
        _handle_domain_error(exc)
    return {"ok": True}


@router.put("/v1/portal/me/favorites/order", tags=["portal-user"])
async def reorder_favorites(
    body: dict[str, Any],
    principal: Principal = Depends(require_principal),
    svc: PortalService = Depends(get_portal_service),
) -> dict[str, Any]:
    ids = body.get("app_ids")
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids) or len(ids) > 200:
        raise _api_error(422, "VALIDATION_ERROR", "app_ids 必须是字符串数组且不超过 200 项")
    items = await svc.reorder_favorites(principal.sub, ids)
    return {"items": items}


# --------------------------------------------------------------------------- # 最近访问
@router.get("/v1/portal/me/recent", tags=["portal-user"])
async def my_recent(
    limit: int = Query(default=10, ge=1, le=100),
    principal: Principal = Depends(require_principal),
    svc: PortalService = Depends(get_portal_service),
) -> dict[str, Any]:
    items = await svc.my_recent(principal.sub, limit=limit)
    return {"items": items, "total": len(items)}


@router.post("/v1/portal/me/recent/{app_id}", tags=["portal-user"])
async def record_visit(
    app_id: str,
    principal: Principal = Depends(require_principal),
    svc: PortalService = Depends(get_portal_service),
) -> dict[str, Any]:
    try:
        visit = await svc.record_visit(principal.sub, app_id)
    except PortalError as exc:
        _handle_domain_error(exc)
    return {"ok": True, "visit": visit}
