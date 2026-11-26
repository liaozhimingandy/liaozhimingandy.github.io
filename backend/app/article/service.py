"""article 服务层：业务编排与事务边界。

分层：API 路由（../article_api.py）通过 Depends(get_article_service) 注入本层；
数据读写只走 dal（BaseDAO + 各表 DAO）；DAO 只 flush 不 commit，
事务出口统一在本层（读操作免提交，写操作完成后显式 commit）。

生成任务模型：
    generate_for_event(event_id) 注册任务并提交 asyncio 后台协程，
    立即返回任务快照；状态推进 queued -> running -> done / failed，
    结果（article_id / uuid / thread_id）落在任务记录里，供前端轮询。
    任务记录是运行时状态（内存），不入库。
    后台协程用 session_scope 开独立会话，不占用请求会话。

并发约束：
    - 同一 event 同时只允许一个进行中任务（queued/running 视为占用）；
    - 全局同一时刻只跑一个生成任务（LLM 串行，避免 AUTO_APPROVE 全局态
      与 checkpoint 连接被并发穿插）。
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from sqlmodel.ext.asyncio.session import AsyncSession

from .dal import ArticleDAO, EventDAO, NewsDAO, RelDAO, TopicDAO
from .models import Article, ArticleEvent, EventMaterial, GenerationTask
from .utils import uuid7

# --------------------------------------------------------------------------- #
# 任务登记（运行时内存状态）
# --------------------------------------------------------------------------- #

_TASKS: dict[str, GenerationTask] = {}      # task_id -> 任务记录
_TASK_ORDER: list[str] = []                 # 插入顺序，用于稳定排序与裁剪

# 全局生成串行锁：同一事件循环内同一时刻只跑一个 LLM 工作流
_GENERATION_LOCK = asyncio.Lock()

MAX_TASK_HISTORY = 200                      # 内存任务记录保留上限

TASK_STATUS_QUEUED = "queued"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_DONE = "done"
TASK_STATUS_FAILED = "failed"

# 正文素材单篇截断长度（字符）
_MATERIAL_TEXT_LIMIT = 6000


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _log(message: str) -> None:
    print(f"[article-service] {message}")


def generator_available() -> dict:
    """生成能力可用性：langgraph 依赖是否装好、LLM_API_KEY 是否配置。"""
    deps_ok = True
    deps_error = ""
    try:
        from . import llm  # noqa: F401  懒加载探测
    except Exception as exc:
        deps_ok = False
        deps_error = f"{type(exc).__name__}: {exc}"
    import os

    api_key_set = bool(os.getenv("LLM_API_KEY"))
    return {
        "deps_ok": deps_ok,
        "deps_error": deps_error,
        "api_key_set": api_key_set,
        "ready": deps_ok and api_key_set,
    }


# --------------------------------------------------------------------------- #
# 服务类：一个请求/一段后台工作的会话 + DAO 集合
# --------------------------------------------------------------------------- #

class ArticleService:
    """article 业务服务。DAO 只 flush，commit/rollback 出口在本类。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.topics = TopicDAO(session)
        self.events = EventDAO(session)
        self.news = NewsDAO(session)
        self.rels = RelDAO(session)
        self.articles = ArticleDAO(session)

    # ---- 话题（event 即"话题"） ----

    async def list_topics(self, limit: int | None = None) -> list[ArticleEvent]:
        """可选话题：已聚合、已有新闻素材的 pending event，按热度排序。"""
        return await self.events.list_pending_materialized(limit=limit)

    async def list_all_topics(self, limit: int = 100) -> list[ArticleEvent]:
        """全部话题（含已生成过文章的），供管理端回看。"""
        return await self.events.list_all(limit=limit)

    async def get_material(self, event_id: int) -> EventMaterial | None:
        """生成素材：事件本体 + 关联新闻正文（每篇截断，标题兜底链接）。"""
        event = await self.events.get_by_id(event_id)
        if event is None:
            return None
        material = EventMaterial.from_event(event)
        news_rows = await self.news.list_by_rel(event_id)
        contents: list[str] = []
        for row in news_rows:
            text = str(row.text or "").strip()
            if len(text) > _MATERIAL_TEXT_LIMIT:
                text = text[:_MATERIAL_TEXT_LIMIT] + "……（正文已截断）"
            title = str(row.title or "").strip()
            contents.append(f"【{title}】\n{text}" if title else text)
        material.source_contents = contents
        if not material.source_urls:
            material.source_urls = [str(row.news_url) for row in news_rows]
        return material

    # ---- 文章查询 ----

    async def list_articles(self, event_id: int | None = None,
                            limit: int = 20) -> list[Article]:
        """文章列表；event_id 给定则只看该事件，默认只看当前版本。"""
        return await self.articles.list_articles(event_id=event_id, limit=limit)

    async def get_article(self, article_uuid: str) -> Article | None:
        return await self.articles.get_by_uuid(article_uuid)

    # ---- 生成结果落库（后台协程调用，独立会话） ----

    async def save_generation_result(self, material: EventMaterial, thread_id: str,
                                     article_uuid: str, state: dict, model_name: str) -> int:
        """把工作流最终 state 写入 article 表，并同步 event 状态；返回文章 id。"""
        event_status = "done" if state.get("final_review") == "pass" else "review"
        article_id = await self.articles.save_new_version({
            "event_id": material.id,
            "uuid": article_uuid,
            "thread_id": thread_id,
            "event_title": material.event_title,
            "outline": state.get("outline", ""),
            "draft": state.get("draft", ""),
            "multi_platform": state.get("multi_platform") or {},
            "check_report": state.get("check_report", ""),
            "final_article": state.get("final_article", ""),
            "images": material.images,
            "source_urls": material.source_urls,
            "model": model_name,
            "status": event_status,
        })
        if article_id:
            await self.events.mark_status(material.id, event_status)
        await self.session.commit()
        return article_id


# --------------------------------------------------------------------------- #
# 任务登记（内存）与后台生成协程
# --------------------------------------------------------------------------- #

def _prune_tasks() -> None:
    """内存任务记录裁剪：只保留最近 MAX_TASK_HISTORY 条。"""
    while len(_TASK_ORDER) > MAX_TASK_HISTORY:
        oldest = _TASK_ORDER.pop(0)
        _TASKS.pop(oldest, None)


def _register_task(event_id: int, event_title: str) -> GenerationTask:
    """登记一个 queued 任务并返回记录。"""
    task_id = f"gen_{int(time.time() * 1000)}_{event_id}"
    task = GenerationTask(
        task_id=task_id,
        event_id=event_id,
        event_title=event_title,
        status=TASK_STATUS_QUEUED,
        created_at=_now(),
    )
    _TASKS[task_id] = task
    _TASK_ORDER.append(task_id)
    _prune_tasks()
    return task


def _update_task(task_id: str, **fields) -> None:
    task = _TASKS.get(task_id)
    if task is not None:
        for key, value in fields.items():
            setattr(task, key, value)


def _get_task_snapshot(task_id: str) -> GenerationTask | None:
    task = _TASKS.get(task_id)
    return task.model_copy(deep=True) if task is not None else None


def _task_in_progress(event_id: int) -> str:
    """返回该 event 进行中任务的 task_id；无则空串。"""
    for tid in reversed(_TASK_ORDER):
        task = _TASKS.get(tid)
        if (
            task is not None
            and task.event_id == event_id
            and task.status in (TASK_STATUS_QUEUED, TASK_STATUS_RUNNING)
        ):
            return tid
    return ""


def _clear_tasks() -> None:
    """测试隔离用：清空内存任务表。"""
    _TASKS.clear()
    _TASK_ORDER.clear()


async def _run_generation(task_id: str, material: EventMaterial,
                          thread_id: str, article_uuid: str) -> None:
    """后台协程体：串行执行 LLM 工作流，结果经独立会话落库。

    始终 auto_approve=True：服务端无交互终端，HITL 断点自动通过，
    审核改为「生成后由人工在文章列表确认」的旁路模式。
    """
    from . import llm  # 懒加载：依赖缺失时在下面统一报错
    from ..core import session_scope

    _update_task(task_id, status=TASK_STATUS_RUNNING, started_at=_now())
    try:
        async with _GENERATION_LOCK:
            state = await asyncio.to_thread(
                llm.run_one, material.model_dump(), thread_id, True,
            )
        if not state:
            raise RuntimeError("生成流程未产出结果（素材缺失或工作流中断）")

        async with session_scope() as session:
            svc = ArticleService(session)
            article_id = await svc.save_generation_result(
                material, thread_id, article_uuid, state, llm.LLM_MODEL,
            )

        _update_task(
            task_id,
            status=TASK_STATUS_DONE,
            finished_at=_now(),
            thread_id=thread_id,
            article_id=article_id,
            article_uuid=article_uuid,
        )
        _log(f"任务完成：{task_id} article={article_id}")
    except Exception as exc:
        _update_task(
            task_id,
            status=TASK_STATUS_FAILED,
            finished_at=_now(),
            error=f"{type(exc).__name__}: {exc}",
        )
        _log(f"任务失败：{task_id} {type(exc).__name__}: {exc}")


async def generate_for_event(event_id: int) -> GenerationTask:
    """为指定 event 启动一次文章生成；立即返回任务快照。

    异常语义（由 API 层转成对应状态码）：
        LookupError   event 不存在或没有素材
        RuntimeError  已有进行中任务 / 生成依赖不可用
    """
    availability = generator_available()
    if not availability["ready"]:
        reason = ("LLM_API_KEY 未配置" if availability["deps_ok"]
                  else availability["deps_error"])
        raise RuntimeError(f"generator_unavailable: {reason}")

    material = await get_material_cached(event_id)
    if material is None:
        raise LookupError(f"event={event_id} 不存在")
    if not material.source_contents and not material.source_urls:
        raise LookupError(f"event={event_id} 没有可用的新闻素材")

    existing = _task_in_progress(event_id)
    if existing:
        raise RuntimeError(f"event_busy: {existing}")

    thread_id = f"event_{event_id}_{uuid7()}"
    article_uuid = str(uuid7())
    task = _register_task(event_id, material.event_title)
    asyncio.create_task(
        _run_generation(task.task_id, material, thread_id, article_uuid),
        name=f"article-gen-{event_id}",
    )
    _log(f"任务已提交：{task.task_id} event={event_id}《{task.event_title}》")
    return _get_task_snapshot(task.task_id) or task


async def get_material_cached(event_id: int) -> EventMaterial | None:
    """为 generate_for_event 开临时会话读素材（后台触发入口使用）。"""
    from ..core import session_scope

    async with session_scope() as session:
        return await ArticleService(session).get_material(event_id)


def get_task(task_id: str) -> GenerationTask | None:
    return _get_task_snapshot(task_id)


def list_tasks(limit: int = 20) -> list[GenerationTask]:
    """最近任务列表（新的在前）。"""
    ordered = list(reversed(_TASK_ORDER))
    return [
        (_TASKS[tid].model_copy(deep=True))
        for tid in ordered[: max(limit, 0)] if tid in _TASKS
    ]


def task_in_progress(event_id: int) -> bool:
    return bool(_task_in_progress(event_id))
