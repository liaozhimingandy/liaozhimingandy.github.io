"""article 服务层：业务编排与事务边界。

分层：API 路由（router.py）通过 Depends(get_article_service) 注入本层；
数据读写只走 dal（BaseDAO + 各表 DAO）；DAO 只 flush 不 commit，
事务出口统一在本层（读操作免提交，写操作完成后显式 commit）。

生成任务模型（持久化）：
    generate_for_event(event_id) 在 article_generation_task 表登记任务并提交
    asyncio 后台协程，立即返回任务快照；状态推进
    queued -> running -> waiting_approval -> running -> done / failed，
    每一步都落库，前端轮询 GET /v1/articles/tasks/{id} 直接查表。

    运行上下文（素材 / thread_id / article_uuid）不存内存：每段开始时凭
    event_id 重读素材、从任务表读检查点标识。进程重启后任务仍在，
    waiting_approval 的任务凭 thread_id 从 LangGraph checkpointer 续跑。

并发约束：
    - 同一 event 同时只允许一个进行中任务（queued/running/waiting_approval 视为占用）；
    - 全局同一时刻只跑一个生成任务（进程内 asyncio.Lock，LLM 串行）；
    - 服务重启时 recover_stale_tasks() 把无人接管的 running/queued 标记失败。
"""


from __future__ import annotations
from ..core.logger import logger

import asyncio
import time
from datetime import datetime, timezone

from sqlmodel.ext.asyncio.session import AsyncSession

from uuid import uuid7

from ..core.config import get_settings
from .dal import ArticleDAO, EventDAO, NewsDAO, RelDAO, TaskDAO, TopicDAO
from .models import (
    Article, ArticleEvent, ArticleGenerationTask, EventMaterial, GenerationTask,
)

# --------------------------------------------------------------------------- #
# 任务登记（持久化到 article_generation_task 表）
# --------------------------------------------------------------------------- #

# 全局生成串行锁：同一事件循环内同一时刻只跑一个 LLM 工作流段。
# 注意这是进程内锁：多实例部署时由 DB 的 in_progress_for_event 兜底同 event 并发，
# 跨实例全局串行需外部队列（当前 LLM 网关本身限速，单实例串行已足够）。
_GENERATION_LOCK = asyncio.Lock()

MAX_TASK_HISTORY = 200                      # 任务表历史保留上限

TASK_STATUS_QUEUED = "queued"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_WAITING_APPROVAL = "waiting_approval"  # HITL：暂停等待前端审批
TASK_STATUS_DONE = "done"
TASK_STATUS_FAILED = "failed"

# 正文素材单篇截断长度（字符）
_MATERIAL_TEXT_LIMIT = 6000


def _now() -> str:
    """任务表时间戳：ISO 8601 + 时区偏移（+00:00）。

    历史实现是无时区的 UTC 字符串，前端 new Date() 会按本地时间解析，
    显示比北京时间早 8 小时；带偏移量后浏览器可直接正确换算。
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log(message: str) -> None:
    logger.info(f"[article-service] {message}")


def generator_available() -> dict:
    """生成能力可用性：langgraph 依赖是否装好、LLM_API_KEY 是否配置。

    密钥判定必须与 llm.py 同源走 Settings 单例——pydantic-settings 从
    backend/.env 读取后不会写回 os.environ，用 os.getenv 会把已配置的密钥
    误判为「未配置」，导致生成接口一直返回 503 GENERATOR_UNAVAILABLE。
    """
    deps_ok = True
    deps_error = ""
    try:
        from . import llm  # noqa: F401  懒加载探测
    except Exception as exc:
        deps_ok = False
        deps_error = f"{type(exc).__name__}: {exc}"

    api_key_set = bool(get_settings().LLM_API_KEY.strip())
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
        thumbnails: list[str] = []
        for row in news_rows:
            text = str(row.text or "").strip()
            if len(text) > _MATERIAL_TEXT_LIMIT:
                text = text[:_MATERIAL_TEXT_LIMIT] + "……（正文已截断）"
            title = str(row.title or "").strip()
            contents.append(f"【{title}】\n{text}" if title else text)
            thumb = str(row.thumbnail or "").strip()
            if thumb:
                thumbnails.append(thumb)
        material.source_contents = contents
        material.thumbnails = thumbnails
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
        """把工作流最终 state 写入 article 表，并同步 event 状态；返回文章 id。

        落库前做配图后处理（illustrate）：素材有图时选出封面并把插图
        均匀插入正文与多平台文章版本；无图则原样保存。
        """
        from . import illustrate

        event_status = "done" if state.get("final_review") == "pass" else "review"
        state = illustrate.illustrate_state(
            state, material.images, material.thumbnails)
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
            "cover_image": state.get("cover_image", ""),
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
# 任务表读写（每个状态变更一个独立短事务，后台协程不占用请求会话）
# --------------------------------------------------------------------------- #

async def _register_task(event_id: int, event_title: str,
                         thread_id: str = "", article_uuid: str = "",
                         need_review: bool = True) -> GenerationTask:
    """在任务表登记一个 queued 任务并返回公共视图。"""
    from ..core import session_scope

    task_id = f"gen_{int(time.time() * 1000)}_{uuid7()}"
    async with session_scope() as session:
        dao = TaskDAO(session)
        row = await dao.create_task(
            task_id, event_id, event_title, _now(), thread_id, article_uuid,
            need_review=need_review,
        )
        await dao.prune(MAX_TASK_HISTORY)
    _log(f"任务已登记：{task_id} event={event_id}")
    return GenerationTask.from_row(row)


async def _update_task(task_id: str, **fields) -> None:
    """局部更新任务字段（字段名对应表列）；任务不存在时静默忽略。"""
    from ..core import session_scope

    async with session_scope() as session:
        await TaskDAO(session).patch(task_id, fields)


async def _get_task_snapshot(task_id: str) -> GenerationTask | None:
    from ..core import session_scope

    async with session_scope() as session:
        row = await TaskDAO(session).get_by_task_id(task_id)
    return GenerationTask.from_row(row) if row is not None else None


async def _task_in_progress(event_id: int) -> str:
    """返回该 event 进行中任务的 task_id；无则空串。"""
    from ..core import session_scope

    async with session_scope() as session:
        row = await TaskDAO(session).in_progress_for_event(event_id)
    return row.task_id if row is not None else ""


async def _clear_tasks() -> None:
    """测试隔离用：清空任务表（生产不会调用）。"""
    from sqlalchemy import delete
    from ..core import session_scope

    async with session_scope() as session:
        await session.exec(delete(ArticleGenerationTask))


async def _pause_for_review(task_id: str, interrupt: dict, thread_id: str,
                            step_name: str) -> str:
    """把任务写入待审状态（HITL 暂停点）。

    正常分段执行（_apply_step_result）与进程重启恢复（recover_stale_tasks
    探测到未答复的 interrupt）共用这一条写库路径，保证审批卡字段一致。
    """
    await _update_task(
        task_id,
        status=TASK_STATUS_WAITING_APPROVAL,
        thread_id=thread_id,
        current_step=str(step_name),
        review_stage=str(interrupt.get("stage", "")),
        review_title=str(interrupt.get("title", "")),
        review_content=str(interrupt.get("content", "")),
        review_options=[str(o) for o in (interrupt.get("options") or [])],
    )
    _log(f"任务等待审核：{task_id} stage={interrupt.get('stage')}")
    return TASK_STATUS_WAITING_APPROVAL


async def _apply_step_result(task_id: str, result: dict, ctx: dict) -> str:
    """把 run_graph_step 的结果落到任务表，返回新的 status。

    paused：写入待审信息与当前节点，任务转 waiting_approval 等前端审批；
    done  ：暂存 state 到 ctx，由 _finalize_done 落库；
    error ：标记失败并记录错误。
    """
    status = result["status"]
    if status == "paused":
        interrupt = dict(result.get("interrupt") or {})
        if not interrupt.get("stage"):
            interrupt["stage"] = str(result.get("stage", ""))
        return await _pause_for_review(
            task_id, interrupt, ctx["thread_id"],
            result.get("last_node") or interrupt.get("stage") or "review",
        )

    if status == "done":
        state = result.get("state") or {}
        if not state:
            return await _fail_task(task_id, "生成流程未产出结果")
        ctx["final_state"] = state
        return "NEEDS_FINALIZE"

    return await _fail_task(task_id, result.get("error_msg") or "生成流程失败")


async def _fail_task(task_id: str, message: str) -> str:
    await _update_task(task_id, status=TASK_STATUS_FAILED, finished_at=_now(),
                       current_step="failed", error=message)
    _log(f"任务失败：{task_id} {message}")
    return TASK_STATUS_FAILED


async def _finalize_done(task_id: str, ctx: dict) -> str:
    """把已完成的 state 落库并标记任务完成（async：含 DB IO）。"""
    from . import llm
    from ..core import session_scope

    state = ctx["final_state"]
    async with session_scope() as session:
        svc = ArticleService(session)
        article_id = await svc.save_generation_result(
            ctx["material"], ctx["thread_id"], ctx["article_uuid"],
            state, llm.LLM_MODEL,
        )
    await _update_task(
        task_id,
        status=TASK_STATUS_DONE,
        finished_at=_now(),
        thread_id=ctx["thread_id"],
        article_id=article_id,
        article_uuid=ctx["article_uuid"],
        current_step="done",
    )
    _log(f"任务完成：{task_id} article={article_id}")
    return TASK_STATUS_DONE


async def _load_run_ctx(task_id: str) -> dict | None:
    """从任务表重建运行上下文：thread_id / article_uuid 读表，素材凭 event_id 重读。

    这是「无内存状态」的关键：暂停与恢复是两次独立 HTTP 请求，甚至可能跨进程
    重启。只要任务表在、checkpointer 在，就能重建出与首次相同的执行上下文。
    """
    from ..core import session_scope

    async with session_scope() as session:
        row = await TaskDAO(session).get_by_task_id(task_id)
    if row is None:
        return None
    material = await get_material_cached(row.event_id)
    if material is None:
        return None
    return {
        "material": material,
        "thread_id": row.thread_id,
        "article_uuid": row.article_uuid,
    }


# 一段工作流的总尝试次数与重试退避：LLM 调用自身有 LLM_RETRIES，
# 这里兜的是 DB/checkpoint 层的瞬时故障（Postgres 重启、网络抖动导致的
# OperationalError: server closed the connection unexpectedly 等）。
SEGMENT_MAX_ATTEMPTS = 3
SEGMENT_RETRY_DELAY = 3.0


async def _has_checkpoint(thread_id: str) -> bool:
    """thread 是否已有 LangGraph checkpoint（可断点续跑）。"""
    from . import llm

    try:
        return await asyncio.to_thread(llm.has_checkpoint, thread_id)
    except Exception:
        return False


async def run_generation_segment(task_id: str, step_input: dict | object | None) -> str:
    """执行一段工作流并更新任务状态，返回新的 status。

    step_input：首次为 initial state dict；resume 由 llm.resume_command 构造；
    None 表示从最后 checkpoint 续跑。

    瞬时故障重试：LangGraph 在每个节点执行前落 checkpoint，节点失败时
    checkpoint 停在「该节点执行前」——重试改传 None 即可从报错节点继续，
    已完成的节点不会重复消耗 LLM 调用。重试耗尽才标记失败。
    """
    from . import llm

    ctx = await _load_run_ctx(task_id)
    if ctx is None or not ctx["thread_id"]:
        return await _fail_task(task_id, "任务记录或检查点标识丢失，请重新生成")

    snapshot = await _get_task_snapshot(task_id)
    running_fields = {"status": TASK_STATUS_RUNNING, "current_step": "running"}
    if snapshot is not None and not snapshot.started_at:
        running_fields["started_at"] = _now()
    await _update_task(task_id, **running_fields)

    first_input = step_input
    result: dict = {}
    for attempt in range(1, SEGMENT_MAX_ATTEMPTS + 1):
        try:
            async with _GENERATION_LOCK:
                result = await asyncio.to_thread(
                    llm.run_graph_step, step_input, ctx["thread_id"],
                )
        except Exception as exc:
            result = {"status": "error", "state": {}, "interrupt": None,
                      "error_msg": f"{type(exc).__name__}: {exc}"}
        if result.get("status") != "error" or attempt >= SEGMENT_MAX_ATTEMPTS:
            break
        # 瞬时故障：退避后从断点续跑；thread 还没有任何 checkpoint（首段
        # 就失败且没落上）时退回用原始输入重试
        await asyncio.sleep(SEGMENT_RETRY_DELAY * attempt)
        step_input = None if await _has_checkpoint(ctx["thread_id"]) else first_input
        _log(f"任务 {task_id} 第 {attempt} 次执行失败，"
             f"{'从断点续跑' if step_input is None else '从头重试'}："
             f"{result.get('error_msg')}")

    new_status = await _apply_step_result(task_id, result, ctx)
    if new_status == "NEEDS_FINALIZE":
        return await _finalize_done(task_id, ctx)
    return new_status


async def generate_for_event(event_id: int, need_review: bool | None = None) -> GenerationTask:
    """为指定 event 启动一次文章生成；立即返回任务快照。

    need_review：是否人工审核；None 时读全局配置 ARTICLE_HITL_ENABLED，
    请求显式传值则优先（前端可按次开关审核）。
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

    existing = await _task_in_progress(event_id)
    if existing:
        raise RuntimeError(f"event_busy: {existing}")

    from . import llm  # 懒加载

    if need_review is None:
        need_review = bool(get_settings().ARTICLE_HITL_ENABLED)

    thread_id = f"event_{event_id}_{uuid7()}"
    article_uuid = str(uuid7())
    # thread_id / article_uuid 随任务一起落表：后续每段从表中读，不存内存。
    task = await _register_task(event_id, material.event_title, thread_id,
                                article_uuid, need_review=bool(need_review))
    _log(f"任务已提交：{task.task_id} event={event_id}《{task.event_title}》"
         f" need_review={need_review}")
    # 首段（生成大纲）是长耗时 LLM 调用，必须在后台任务里跑，
    # 否则 POST 会阻塞到大纲生成完，前端 15s fetch 超时会误报失败。
    async def _run_first_segment() -> None:
        await run_generation_segment(
            task.task_id,
            llm.initial_state_from_material(
                material.model_dump(), need_review=bool(need_review),
            ),
        )

    asyncio.create_task(_run_first_segment(), name=f"article-gen-first-{event_id}")
    return await _get_task_snapshot(task.task_id) or task


async def resume_generation(task_id: str, decision: str, suggest: str = "") -> GenerationTask:
    """前端审批后，从暂停点恢复工作流继续跑。

    decision: pass / modify / reject（由 API 层校验）；suggest 为修改意见。
    返回更新后的任务快照。异常语义：LookupError 任务不存在 / 不在等待态；
    RuntimeError 并发冲突。
    """
    from . import llm

    task = await _get_task_snapshot(task_id)
    if task is None:
        raise LookupError(f"任务不存在：{task_id}")
    if task.status != TASK_STATUS_WAITING_APPROVAL:
        raise RuntimeError(f"任务不在等待审核状态：{task.status}")

    step_input = llm.resume_command(decision, suggest)
    # 下一段生成是数分钟级 LLM 调用，必须后台执行、POST 立即返回：
    # 同步等待会撞上前端 15s fetch 超时，被误报为「网络错误」，
    # 而工作流其实还在正常跑（前端却已标记失败并停轮询）。
    await _update_task(task_id, status=TASK_STATUS_RUNNING, current_step="running")

    async def _run_resume_segment() -> None:
        await run_generation_segment(task_id, step_input)

    asyncio.create_task(_run_resume_segment(), name=f"article-gen-resume-{task_id}")
    return await _get_task_snapshot(task_id) or task


async def get_material_cached(event_id: int) -> EventMaterial | None:
    """为 generate_for_event 开临时会话读素材（后台触发入口使用）。"""
    from ..core import session_scope

    async with session_scope() as session:
        return await ArticleService(session).get_material(event_id)


async def get_task(task_id: str) -> GenerationTask | None:
    """查询单个任务（前端轮询入口，直接查表）。"""
    return await _get_task_snapshot(task_id)


async def list_tasks(limit: int = 20) -> list[GenerationTask]:
    """最近任务列表（新的在前，查表）。"""
    from ..core import session_scope

    async with session_scope() as session:
        rows = await TaskDAO(session).list_recent(limit)
    return [GenerationTask.from_row(row) for row in rows]


async def task_in_progress(event_id: int) -> bool:
    return bool(await _task_in_progress(event_id))


async def recover_stale_tasks() -> int:
    """服务启动时接续上次进程遗留的 running/queued 任务（断点续跑）。

    处理策略（尽量从报错节点继续，而不是一律标失败让用户重来）：
      - checkpoint 停在未答复的 interrupt：还原成 waiting_approval，等前端审批；
      - checkpoint 存在：传 None 续跑，LangGraph 重跑最后未完成的节点；
      - 无 checkpoint（queued 或首段没跑过）：凭任务表的 need_review 从头跑首段；
      - 素材已被清理：标记失败并写明原因；
      - waiting_approval 不动——本就在等前端审批。
    返回接续（或还原待审）的任务数。
    """
    from . import llm
    from ..core import session_scope

    async with session_scope() as session:
        rows = await TaskDAO(session).list_stale()

    resumed = 0
    for row in rows:
        thread_id = row.thread_id or ""
        interrupt: dict | None = None
        has_cp = False
        if thread_id:
            try:
                has_cp = await _has_checkpoint(thread_id)
                if has_cp:
                    interrupt = await asyncio.to_thread(
                        llm.pending_interrupt, thread_id)
            except Exception as exc:
                _log(f"任务 {row.task_id} 检查点探测失败："
                     f"{type(exc).__name__}: {exc}")

        if interrupt:
            # 进程死在「工作流已暂停等审核」与「任务状态写库」之间：还原审批卡
            await _pause_for_review(
                row.task_id, interrupt, thread_id,
                str(interrupt.get("stage", "")) or "review",
            )
            resumed += 1
            continue

        if has_cp:
            step_input: dict | None = None       # 从断点续跑
        else:
            material = await get_material_cached(row.event_id)
            if material is None:
                await _fail_task(row.task_id, "服务重启后话题素材已被清理，无法继续生成")
                continue
            step_input = llm.initial_state_from_material(
                material.model_dump(), need_review=bool(row.need_review))

        _log(f"启动恢复：接续任务 {row.task_id}（{row.status} -> running）")
        asyncio.create_task(
            run_generation_segment(row.task_id, step_input),
            name=f"article-gen-recover-{row.task_id}",
        )
        resumed += 1

    if resumed:
        _log(f"启动恢复：{resumed} 个中断任务已接续执行")
    return resumed


async def retry_task(task_id: str) -> GenerationTask:
    """失败任务重试：有 checkpoint 从报错节点续跑，否则从头跑首段。

    用户在任务中心点「重试」的入口。异常语义：
    LookupError 任务不存在；RuntimeError 任务不是失败态 / 同 event 已有进行中任务。
    """
    from . import llm

    task = await _get_task_snapshot(task_id)
    if task is None:
        raise LookupError(f"任务不存在：{task_id}")
    if task.status != TASK_STATUS_FAILED:
        raise RuntimeError(f"任务不是失败状态，无法重试：{task.status}")
    existing = await _task_in_progress(task.event_id)
    if existing:
        raise RuntimeError(f"event_busy: {existing}")

    has_cp = bool(task.thread_id) and await _has_checkpoint(task.thread_id)
    interrupt: dict | None = None
    if has_cp:
        try:
            interrupt = await asyncio.to_thread(llm.pending_interrupt, task.thread_id)
        except Exception:
            interrupt = None
    if interrupt:
        # 失败其实停在了审核点（状态写库前进程挂了）：还原审批卡即可
        await _pause_for_review(
            task_id, interrupt, task.thread_id,
            str(interrupt.get("stage", "")) or "review",
        )
        return await _get_task_snapshot(task_id) or task

    if has_cp:
        step_input: dict | None = None
    else:
        material = await get_material_cached(task.event_id)
        if material is None:
            raise LookupError("话题素材已被清理，无法重试")
        step_input = llm.initial_state_from_material(
            material.model_dump(), need_review=bool(task.need_review))

    await _update_task(task_id, status=TASK_STATUS_RUNNING, error="",
                       finished_at="", current_step="running")
    asyncio.create_task(
        run_generation_segment(task_id, step_input),
        name=f"article-gen-retry-{task_id}",
    )
    return await _get_task_snapshot(task_id) or task


# 存量时间列升级清单：表名 -> 需改为 timestamptz 的列
_TIME_COLUMNS: dict[str, tuple[str, ...]] = {
    "article_topic": ("fetch_time",),
    "article_event": ("first_seen", "last_seen"),
    "article_news": ("create_time",),
    "article": ("create_time", "update_time"),
}


async def migrate_time_columns() -> None:
    """把存量 Postgres 时间列从 naive timestamp 升级为 timestamptz（幂等）。

    背景：历史模型存 naive UTC（无时区标记），DB 里数值比北京时间少 8 小时，
    排查问题时极易误读。新库由 create_all 直接建成带时区类型；已存在的列
    create_all 不会改结构，这里显式 ALTER，原值按 UTC 解释（USING ... AT TIME
    ZONE 'UTC'）。只升级 naive 列（先查 information_schema），已是 timestamptz
    的列不动，避免二次 AT TIME ZONE 换算引入偏移。SQLite（内存/降级引擎）跳过。
    """
    from sqlalchemy import text
    from ..core.database import get_engine

    engine = get_engine()
    if engine.url.get_backend_name() != "postgresql":
        return
    async with engine.begin() as conn:
        for table, columns in _TIME_COLUMNS.items():
            for column in columns:
                try:
                    res = await conn.execute(text(
                        "SELECT data_type FROM information_schema.columns "
                        "WHERE table_name = :t AND column_name = :c "
                        "AND table_schema = current_schema()",
                    ), {"t": table, "c": column})
                    if res.scalar() != "timestamp without time zone":
                        continue  # 已带时区或列不存在（新库 create_all 已建对）
                    sql = (
                        f"ALTER TABLE {table} ALTER COLUMN {column} "
                        f"TYPE timestamptz USING {column} AT TIME ZONE 'UTC'"
                    )
                    await conn.execute(text(sql))
                    _log(f"时间列已升级为 timestamptz：{table}.{column}")
                except Exception as exc:
                    # 迁移失败不阻断启动：最坏情况是旧列继续存 naive UTC
                    _log(f"时间列迁移跳过 {table}.{column}：{type(exc).__name__}: {exc}")


async def migrate_article_columns() -> None:
    """给存量 article 表补 cover_image 列（幂等，只对 Postgres 执行）。

    create_all 只建表不加列：历史库的 article 没有 cover_image 列，
    配图后处理落库时需要它。
    """
    from sqlalchemy import text
    from ..core.database import get_engine

    engine = get_engine()
    if engine.url.get_backend_name() != "postgresql":
        return
    async with engine.begin() as conn:
        try:
            await conn.execute(text(
                "ALTER TABLE article "
                "ADD COLUMN IF NOT EXISTS cover_image TEXT NOT NULL DEFAULT ''",
            ))
            _log("article 表 cover_image 列就绪")
        except Exception as exc:
            _log(f"article 表列迁移跳过：{type(exc).__name__}: {exc}")


async def migrate_task_columns() -> None:
    """给存量任务表补 need_review 列（幂等，只对 Postgres 执行）。

    create_all 只建表不加列：历史库的 article_generation_task 没有
    need_review 列，重启续跑 queued 任务时需要它重建首段输入。
    """
    from sqlalchemy import text
    from ..core.database import get_engine

    engine = get_engine()
    if engine.url.get_backend_name() != "postgresql":
        return
    async with engine.begin() as conn:
        try:
            await conn.execute(text(
                "ALTER TABLE article_generation_task "
                "ADD COLUMN IF NOT EXISTS need_review BOOLEAN NOT NULL DEFAULT TRUE",
            ))
            _log("任务表 need_review 列就绪")
        except Exception as exc:
            _log(f"任务表列迁移跳过：{type(exc).__name__}: {exc}")
