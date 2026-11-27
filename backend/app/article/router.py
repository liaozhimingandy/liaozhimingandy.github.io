"""article 流水线 REST API（路由层）。

分层：只做参数校验、权限判定、调用服务层（service.ArticleService，经
Depends 链 get_session -> ArticleService 注入）、模型 -> 公共 JSON 的映射；
不含业务逻辑，不直接触碰 DAO/collector/llm。

权限模型：
    话题/文章读接口    公开可读（内容本身会对外展示）；
    触发生成           登录用户即可（ARTICLE_GENERATE_REQUIRE_ADMIN=1 时要求管理员）；
    手动采集/聚合      仅管理员（require_admin，白名单为空 fail-closed）。

生成是长任务：POST 立即返回 task_id，前端轮询任务状态；
同一 event 同时只允许一个进行中任务，全局同一时刻只跑一个生成。

由 app.article 包在上一级统一导出（from app.article import router）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from .. import config
from ..auth import Principal
from ..core.database import get_session
from ..portal.router import (
    _api_error,
    optional_principal,
    require_admin,
    require_principal,
)
from . import scheduler, service
from .models import Article, ArticleEvent, GenerationTask
from .service import ArticleService

router = APIRouter()


async def get_article_service(
    session: AsyncSession = Depends(get_session),
) -> ArticleService:
    """DI 链：请求级会话 -> 服务对象（DAO 集合随会话构建）。"""
    return ArticleService(session)


# --------------------------------------------------------------------------- #
# 请求/响应模型
# --------------------------------------------------------------------------- #

class GenerateRequest(BaseModel):
    event_id: int = Field(ge=1, description="要生成文章的聚合事件 id")
    need_review: bool | None = Field(
        default=None,
        description="是否人工审核（大纲/终审）；不传用服务端 ARTICLE_HITL_ENABLED 配置",
    )


class TopicItem(BaseModel):
    event_id: int
    event_title: str
    event_summary: str
    total_score: int
    status: str
    source_urls: list[str]
    images: list[dict[str, Any]]
    generating: bool
    # 素材的采集源（如 百度/微博/36氪），去重保序；前端展示标签与筛选
    sources: list[str] = Field(default_factory=list)


async def _topic_item(
    event: ArticleEvent, sources: list[str] | None = None,
) -> TopicItem:
    """ArticleEvent 表模型 -> 话题公共视图（generating 需查任务表）。"""
    return TopicItem(
        event_id=int(event.id or 0),
        event_title=event.event_title,
        event_summary=event.event_summary or "",
        total_score=event.total_score,
        status=event.status,
        source_urls=[str(u) for u in (event.source_urls or [])],
        images=[dict(i) for i in (event.images or []) if isinstance(i, dict)],
        generating=await service.task_in_progress(int(event.id or 0)),
        sources=list(sources or []),
    )


def _task_public(task: GenerationTask) -> dict[str, Any]:
    """GenerationTask 模型 -> 任务公共视图。"""
    return task.model_dump(exclude_none=True)


def _article_public(article: Article) -> dict[str, Any]:
    """Article 模型 -> 文章公共视图（时间统一 ISO 字符串）。"""
    return article.model_dump(mode="json", exclude_none=True)


# --------------------------------------------------------------------------- #
# 话题（event）——外部用户选择的话题列表
# --------------------------------------------------------------------------- #

@router.get("/v1/articles/topics", tags=["article"])
async def list_topics(
    limit: int = Query(default=50, ge=1, le=200),
    svc: ArticleService = Depends(get_article_service),
    principal: Principal | None = Depends(optional_principal),
) -> dict[str, Any]:
    """可选话题：已聚合、已有新闻素材的 pending 事件，按热度排序。"""
    try:
        items = await svc.list_topics(limit=limit)
    except Exception as exc:
        raise _api_error(503, "ARTICLE_DB_ERROR", f"话题加载失败：{exc}") from None
    # 采集源一次批量查齐（联表），避免逐话题查库
    try:
        sources = await svc.news.sources_by_event(
            [int(e.id or 0) for e in items])
    except Exception:
        sources = {}
    return {
        "items": [
            (await _topic_item(event, sources.get(int(event.id or 0)))).model_dump()
            for event in items
        ],
        "total": len(items),
    }


# --------------------------------------------------------------------------- #
# 生成任务
# --------------------------------------------------------------------------- #

def _require_generate_permission(principal: Principal) -> None:
    if config.article_generate_require_admin():
        require_admin(principal)


@router.post("/v1/articles/generate", tags=["article"])
async def generate_article(
    body: GenerateRequest,
    principal: Principal = Depends(require_principal),
) -> dict[str, Any]:
    """选择话题（event）触发生成；立即返回任务描述，前端轮询任务状态。"""
    _require_generate_permission(principal)
    try:
        task = await service.generate_for_event(body.event_id, body.need_review)
    except LookupError as exc:
        raise _api_error(404, "EVENT_NOT_FOUND", str(exc)) from None
    except RuntimeError as exc:
        message = str(exc)
        if message.startswith("generator_unavailable"):
            raise _api_error(503, "GENERATOR_UNAVAILABLE",
                             message.split(": ", 1)[-1]) from None
        if message.startswith("event_busy:"):
            raise _api_error(
                409, "EVENT_GENERATING",
                "该话题已有生成任务进行中",
                extra={"task_id": message.split(": ", 1)[-1]},
            ) from None
        raise _api_error(500, "GENERATE_ERROR", message) from None
    return _task_public(task)


@router.get("/v1/articles/tasks", tags=["article"])
async def list_tasks(
    limit: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(require_principal),
) -> dict[str, Any]:
    """最近的生成任务列表（新的在前，直接查任务表）。"""
    return {"items": [_task_public(t) for t in await service.list_tasks(limit=limit)]}


@router.get("/v1/articles/tasks/{task_id}", tags=["article"])
async def get_task(
    task_id: str,
    principal: Principal = Depends(require_principal),
) -> dict[str, Any]:
    task = await service.get_task(task_id)
    if task is None:
        raise _api_error(404, "TASK_NOT_FOUND", f"任务不存在：{task_id}")
    return _task_public(task)


class ReviewRequest(BaseModel):
    decision: str = Field(description="审核决定：pass / modify / reject")
    suggest: str = Field(default="", description="修改意见，decision=modify 时必填")


@router.post("/v1/articles/tasks/{task_id}/review", tags=["article"])
async def review_task(
    task_id: str,
    body: ReviewRequest,
    principal: Principal = Depends(require_principal),
) -> dict[str, Any]:
    """HITL：前端审批后从断点恢复工作流。

    decision 非法、或修改决定缺意见时返回 422；任务不存在/不在等待态返回 409。
    """
    decision = body.decision.strip().lower()
    if decision not in ("pass", "modify", "reject"):
        raise _api_error(422, "INVALID_REVIEW", "decision 必须是 pass / modify / reject")
    if decision == "modify" and not body.suggest.strip():
        raise _api_error(422, "REVIEW_SUGGEST_REQUIRED", "修改决定必须填写修改意见")
    try:
        task = await service.resume_generation(task_id, decision, body.suggest.strip())
    except LookupError as exc:
        raise _api_error(404, "TASK_NOT_FOUND", str(exc)) from None
    except RuntimeError as exc:
        raise _api_error(409, "TASK_NOT_WAITING", str(exc)) from None
    return _task_public(task)


@router.post("/v1/articles/tasks/{task_id}/retry", tags=["article"])
async def retry_task(
    task_id: str,
    principal: Principal = Depends(require_principal),
) -> dict[str, Any]:
    """失败任务重试：有 checkpoint 从报错节点续跑，否则从头跑首段。"""
    try:
        task = await service.retry_task(task_id)
    except LookupError as exc:
        raise _api_error(404, "TASK_NOT_FOUND", str(exc)) from None
    except RuntimeError as exc:
        message = str(exc)
        if message.startswith("event_busy:"):
            raise _api_error(409, "EVENT_GENERATING",
                             "该话题已有任务进行中") from None
        raise _api_error(409, "TASK_NOT_RETRYABLE", message) from None
    return _task_public(task)


# --------------------------------------------------------------------------- #
# 文章
# --------------------------------------------------------------------------- #

@router.get("/v1/articles", tags=["article"])
async def list_articles(
    event_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    svc: ArticleService = Depends(get_article_service),
    principal: Principal | None = Depends(optional_principal),
) -> dict[str, Any]:
    """文章列表（不含正文大字段）；event_id 过滤，默认只看当前版本。"""
    items = await svc.list_articles(event_id=event_id, limit=limit)
    return {"items": [_article_public(a) for a in items], "total": len(items)}


# --------------------------------------------------------------------------- #
# 管理端：手动触发采集/聚合、调度器状态
# --------------------------------------------------------------------------- #

@router.get("/v1/articles/scheduler", tags=["article-admin"])
async def scheduler_status(admin: Principal = Depends(require_admin)) -> dict[str, Any]:
    """调度器运行状态与最近一次采集/聚合结果。"""
    return scheduler.status()


@router.post("/v1/articles/admin/collect", tags=["article-admin"])
async def manual_collect(admin: Principal = Depends(require_admin)) -> dict[str, Any]:
    """手动执行一轮采集（与定时任务互斥；正在采集时返回 409）。"""
    try:
        stats = await scheduler.run_collect_now()
    except RuntimeError:
        raise _api_error(409, "COLLECT_BUSY", "采集正在执行中，请稍后再试") from None
    except Exception as exc:
        raise _api_error(500, "COLLECT_FAILED", f"采集失败：{exc}") from None
    return {"ok": True, "stats": stats}


@router.post("/v1/articles/admin/cluster", tags=["article-admin"])
async def manual_cluster(admin: Principal = Depends(require_admin)) -> dict[str, Any]:
    """手动执行一轮聚合（与定时任务互斥；正在聚合时返回 409）。"""
    try:
        pending = await scheduler.run_cluster_now()
    except RuntimeError:
        raise _api_error(409, "CLUSTER_BUSY", "聚合正在执行中，请稍后再试") from None
    except Exception as exc:
        raise _api_error(500, "CLUSTER_FAILED", f"聚合失败：{exc}") from None
    return {"ok": True, "pending_topics_before": pending}


@router.get("/v1/articles/generator", tags=["article-admin"])
async def generator_status(admin: Principal = Depends(require_admin)) -> dict[str, Any]:
    """生成能力可用性：依赖安装情况与 LLM_API_KEY 配置状态。"""
    availability = service.generator_available()
    return {
        "ready": availability["ready"],
        "deps_ok": availability["deps_ok"],
        "api_key_set": availability["api_key_set"],
        "require_admin": config.article_generate_require_admin(),
    }


# 注意：/{article_uuid} 详情路由必须放在所有字面量路由之后，
# 否则 /v1/articles/scheduler、/v1/articles/generator 会被它抢先匹配成 uuid。
@router.get("/v1/articles/{article_uuid}", tags=["article"])
async def get_article(
    article_uuid: str,
    svc: ArticleService = Depends(get_article_service),
    principal: Principal | None = Depends(optional_principal),
) -> dict[str, Any]:
    """文章详情：定稿、大纲、多平台版本、质检报告全量字段。"""
    article = await svc.get_article(article_uuid)
    if article is None:
        raise _api_error(404, "ARTICLE_NOT_FOUND", "文章不存在")
    return _article_public(article)
