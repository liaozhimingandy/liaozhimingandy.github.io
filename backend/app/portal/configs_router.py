"""公共配置表 API（多工具共享，零知识密文同步）。

路由（统一 /v1 前缀）：
  GET    /v1/auth/mode                      当前鉴权模式与风险提示
  GET    /v1/tools                          列出启用工具（注册表）
  GET    /v1/tools/{tool_id}                单个工具元信息
  GET    /v1/configs/{tool_id}/_quota       配额使用情况（工具覆盖值优先）
  GET    /v1/configs/{tool_id}              列出该工具下当前用户全部配置
  GET    /v1/configs/{tool_id}/{key}        取单条（返回 ETag）
  PUT    /v1/configs/{tool_id}/{key}        UPSERT（乐观锁 CAS）
  DELETE /v1/configs/{tool_id}/{key}        软删除（乐观锁 CAS）

分层：路由只做参数/形状校验与身份注入；业务在 portal/service.ConfigService；
数据读写经 Depends(get_session) -> DAO。注意 _quota 路由必须在 {tool_id}/{key} 之前。

安全契约（贯穿本文件）：
  1. user_sub 只来自鉴权 provider，任何 path/query/body 里的用户标识一律忽略。
  2. value 是不透明 blob：本层只做「大小上限」与 JSON 可序列化校验，
     不解析结构、不解密、不记录内容，日志里也不出现 value。
  3. 乐观锁用 expected_revision 做 CAS，防多端同步的丢失更新。
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from ..core.config import get_settings
from ..core.database import get_session
from ..schemas import (
    AuthModeResponse,
    ConfigListResponse,
    ConfigPutRequest,
    ConfigRecordResponse,
    ConflictDetail,
    KEY_PATTERN,
    QuotaResponse,
    TOOL_ID_PATTERN,
    ToolListResponse,
    ToolRecordResponse,
)
from .models import ConflictError, NotFoundError, PortalError
from .router import _api_error, get_auth_provider, get_portal_service, require_principal
from .service import ConfigService, PortalService, QuotaExceededError

router = APIRouter()

_TOOL_RE = re.compile(TOOL_ID_PATTERN)
_KEY_RE = re.compile(KEY_PATTERN)
_RESERVED_KEYS = {"_quota"}


# --------------------------------------------------------------------------- #
# 依赖
# --------------------------------------------------------------------------- #

async def get_config_service(
    session: AsyncSession = Depends(get_session),
) -> ConfigService:
    return ConfigService(session)


def _validate_ids(
    tool_id: str,
    key: str | None = None,
) -> None:
    """校验 tool_id/key 形状 + 保留 key。

    工具准入（portal_apps 权威）+ AP_TOOL_IDS 部署级白名单由各路由
    await portal_svc 判定（异步会话）。
    """
    if not _TOOL_RE.match(tool_id):
        raise _api_error(400, "INVALID_TOOL_ID", "tool_id 形状非法")
    if key is not None:
        if not _KEY_RE.match(key) or key in _RESERVED_KEYS:
            raise _api_error(400, "INVALID_KEY", "key 形状非法或为保留字")


def _validate_value(value: Any) -> None:
    """零知识边界内的最小校验：可 JSON 序列化 + 大小上限。绝不解析业务语义。"""
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        raise _api_error(422, "INVALID_VALUE", "value 必须是可 JSON 序列化的值") from None
    if len(text.encode("utf-8")) > get_settings().AP_MAX_VALUE_BYTES:
        raise _api_error(413, "VALUE_TOO_LARGE", "value 超过大小上限")


def _to_response(rec: dict[str, Any]) -> ConfigRecordResponse:
    rev = rec["revision"]
    return ConfigRecordResponse(
        tool_id=rec["tool_id"],
        key=rec["key"],
        value=rec["value"],
        revision=rev,
        schema_version=rec.get("schema_version", 1),
        updated_by_device=rec.get("updated_by_device"),
        created_at=rec["created_at"],
        updated_at=rec["updated_at"],
        deleted_at=rec.get("deleted_at"),
        etag=f'W/"{rev}"',
    )


# --------------------------------------------------------------------------- #
# 路由
# --------------------------------------------------------------------------- #

@router.get("/v1/auth/mode", response_model=AuthModeResponse, tags=["configs"])
async def auth_mode_endpoint(
    provider: Any = Depends(get_auth_provider),
) -> AuthModeResponse:
    """暴露鉴权模式，便于前端/运维识别 passthrough/dev/stub 的不安全状态。"""
    secure = provider.mode == "logto" and bool(getattr(provider, "configured", False))
    warning = None
    if provider.mode == "passthrough":
        warning = (
            "暂时不鉴权：服务端信任客户端声明的 X-User-Sub，任何人可伪造身份读写云端密文；"
            "value 为零知识密文无法被解密，但可被覆盖/删除。正式上线前请切 AP_AUTH_MODE=logto"
        )
    elif provider.mode == "dev":
        warning = "开发鉴权模式：X-User-Sub 头被信任，切勿用于生产"
    elif provider.mode == "stub":
        warning = "测试桩鉴权模式：所有请求共用固定身份"
    elif provider.mode == "logto" and not secure:
        warning = "Logto 未配置完整，所有请求将被拒绝（fail-closed）"
    return AuthModeResponse(
        mode=provider.mode,
        secure=secure,
        logto_configured=bool(getattr(provider, "configured", False)),
        warning=warning,
    )


@router.get("/v1/tools", response_model=ToolListResponse, tags=["tools"])
async def list_tools(
    principal: Any = Depends(require_principal),
    svc: PortalService = Depends(get_portal_service),
) -> ToolListResponse:
    """列出启用中的工具（注册表）。需鉴权，但不含任何用户数据。"""
    items = [ToolRecordResponse(**t.to_public()) for t in await svc.list_tools()]
    return ToolListResponse(items=items, count=len(items))


@router.get("/v1/tools/{tool_id}", response_model=ToolRecordResponse, tags=["tools"])
async def get_tool(
    tool_id: str,
    principal: Any = Depends(require_principal),
    svc: PortalService = Depends(get_portal_service),
) -> ToolRecordResponse:
    """单个工具元信息。已禁用工具返回 404（不泄露存在性）。"""
    t = await svc.get_tool(tool_id)
    if t is None or not t.enabled:
        raise _api_error(404, "TOOL_NOT_FOUND", "工具不存在或未启用")
    return ToolRecordResponse(**t.to_public())


@router.get("/v1/configs/{tool_id}/_quota", response_model=QuotaResponse, tags=["configs"])
async def quota(
    tool_id: str,
    principal: Any = Depends(require_principal),
    config_svc: ConfigService = Depends(get_config_service),
    portal_svc: PortalService = Depends(get_portal_service),
) -> QuotaResponse:
    if not _TOOL_RE.match(tool_id):
        raise _api_error(400, "INVALID_TOOL_ID", "tool_id 形状非法")
    if not await portal_svc.exists_enabled(tool_id):
        raise _api_error(404, "TOOL_NOT_FOUND", "工具不存在或未启用")
    settings = get_settings()
    max_keys, max_bytes = await portal_svc.resolve_quota(
        tool_id,
        max_keys=max(1, int(settings.AP_MAX_KEYS)),
        max_bytes=max(1, int(settings.AP_MAX_VALUE_BYTES)),
    )
    rows = await config_svc.list(principal.sub, tool_id)
    return QuotaResponse(
        tool_id=tool_id,
        key_count=len(rows),
        max_keys=max_keys,
        max_value_bytes=max_bytes,
    )


@router.get("/v1/configs/{tool_id}", response_model=ConfigListResponse, tags=["configs"])
async def list_configs(
    tool_id: str,
    include_deleted: bool = False,
    principal: Any = Depends(require_principal),
    config_svc: ConfigService = Depends(get_config_service),
    portal_svc: PortalService = Depends(get_portal_service),
) -> ConfigListResponse:
    _validate_ids(tool_id)
    if not await portal_svc.exists_enabled(tool_id):
        raise _api_error(404, "TOOL_NOT_FOUND", "工具不存在或未启用")
    rows = await config_svc.list(principal.sub, tool_id, include_deleted=include_deleted)
    items = [_to_response(r) for r in rows]
    return ConfigListResponse(tool_id=tool_id, items=items, count=len(items))


@router.get("/v1/configs/{tool_id}/{key}", response_model=ConfigRecordResponse, tags=["configs"])
async def get_config(
    tool_id: str,
    key: str,
    response: Response,
    principal: Any = Depends(require_principal),
    config_svc: ConfigService = Depends(get_config_service),
    portal_svc: PortalService = Depends(get_portal_service),
) -> ConfigRecordResponse:
    _validate_ids(tool_id, key)
    if not await portal_svc.exists_enabled(tool_id):
        raise _api_error(404, "TOOL_NOT_FOUND", "工具不存在或未启用")
    try:
        rec = await config_svc.get(principal.sub, tool_id, key)
    except NotFoundError:
        raise _api_error(404, "NOT_FOUND", "配置不存在") from None
    resp = _to_response(rec)
    # ETag 走响应头也放一份，供标准 If-Match 客户端使用
    response.headers["ETag"] = resp.etag
    return resp


@router.put("/v1/configs/{tool_id}/{key}", response_model=ConfigRecordResponse, tags=["configs"])
async def put_config(
    tool_id: str,
    key: str,
    body: ConfigPutRequest,
    response: Response,
    principal: Any = Depends(require_principal),
    config_svc: ConfigService = Depends(get_config_service),
    portal_svc: PortalService = Depends(get_portal_service),
) -> ConfigRecordResponse:
    _validate_ids(tool_id, key)
    if not await portal_svc.exists_enabled(tool_id):
        raise _api_error(404, "TOOL_NOT_FOUND", "工具不存在或未启用")
    _validate_value(body.value)
    settings = get_settings()
    max_keys, max_bytes = await portal_svc.resolve_quota(
        tool_id,
        max_keys=max(1, int(settings.AP_MAX_KEYS)),
        max_bytes=max(1, int(settings.AP_MAX_VALUE_BYTES)),
    )
    # 单条 value 大小也要用工具覆盖后的上限复核（不解析内容，只量字节）
    if len(json.dumps(body.value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > max_bytes:
        raise _api_error(413, "VALUE_TOO_LARGE", "value 超过该工具的大小上限")

    try:
        rec = await config_svc.put(
            principal.sub, tool_id, key, body.value,
            expected_revision=body.expected_revision,
            schema_version=body.schema_version,
            updated_by_device=body.updated_by_device,
            max_keys=max_keys,
        )
    except QuotaExceededError as exc:
        raise _api_error(409, "QUOTA_EXCEEDED", str(exc)) from None
    except ConflictError as exc:
        raise _api_error(
            409, "REVISION_CONFLICT",
            "版本冲突：资源已被其他端更新",
            detail=ConflictDetail(expected=exc.expected, actual=exc.actual).model_dump(),
        ) from None
    except PortalError as exc:
        raise _api_error(exc.status_code, exc.code, str(exc)) from None
    resp = _to_response(rec)
    response.headers["ETag"] = resp.etag
    return resp


@router.delete("/v1/configs/{tool_id}/{key}", response_model=ConfigRecordResponse, tags=["configs"])
async def delete_config(
    tool_id: str,
    key: str,
    expected_revision: int = Query(..., ge=1, description="乐观锁期望版本（当前 revision）"),
    principal: Any = Depends(require_principal),
    config_svc: ConfigService = Depends(get_config_service),
    portal_svc: PortalService = Depends(get_portal_service),
) -> ConfigRecordResponse:
    _validate_ids(tool_id, key)
    if not await portal_svc.exists_enabled(tool_id):
        raise _api_error(404, "TOOL_NOT_FOUND", "工具不存在或未启用")
    try:
        rec = await config_svc.delete(principal.sub, tool_id, key, expected_revision)
    except ConflictError as exc:
        raise _api_error(
            409, "REVISION_CONFLICT",
            "版本冲突：资源已被其他端更新",
            detail=ConflictDetail(expected=exc.expected, actual=exc.actual).model_dump(),
        ) from None
    except NotFoundError:
        raise _api_error(404, "NOT_FOUND", "配置不存在或已删除") from None
    except PortalError as exc:
        raise _api_error(exc.status_code, exc.code, str(exc)) from None
    return _to_response(rec)
