"""独立常驻 worker 进程：轮询任务表 + ThreadPoolExecutor 执行 LangGraph 任务段。

用法（与 API 进程分开部署，ARTICLE_EXECUTION_MODE=worker 时启用）：
    python -m app.article.worker

架构（与用户规划一致）：
    article_generation_task 表就是队列——
      API 进程（FastAPI）：只做业务登记（POST /generate 入队 queued）、
        审批决定落表（POST /review 写 review_decision 后置回 queued）、
        失败重试重新入队；不执行任何 LangGraph 代码；
      worker 进程（本模块）：常驻循环轮询任务表 -> CAS 领取（DB 行级裁决，
        多 worker 并发抢任务也只有一个成功）-> 在 ThreadPoolExecutor 里经
        GraphService 执行图段 -> 段级落库（状态/当前节点/心跳）。

双调用入口共用 GraphService（app/article/graph/service.py）：
    路由层 service.py（inline 模式）与 worker 线程传各自的参数调同一个门面：
        service.run_generation_segment(task_id, step_input, executor=None, serialize=True)
        worker   run_generation_segment(task_id, step_input, executor=线程池, serialize=False)

领取协议（DB 状态机，见 TaskDAO.claim / list_claimable）：
    queued      新任务 / 审批决定已记录 / 手动重试 -> 可领取；
    running     heartbeat_at 超过 ARTICLE_WORKER_STALE_SECONDS（或为空）视为
                前执行者失联 -> 可接管（checkpoint 在，从断点续跑）；
    waiting_approval / done / failed 不领取（等审批 / 已完结）。

领取后按现场规划下一段输入（_plan_task）：
    有未消费的 review_decision 且 checkpoint 停在 interrupt
        -> resume Command（先清决定字段，防崩溃后重复消费）；
    checkpoint 停在未答复 interrupt（无决定）-> 还原 waiting_approval 审批卡；
    有 checkpoint 无 interrupt -> 传 None 从断点续跑；
    无 checkpoint -> 凭任务表 need_review 从头构造首段 initial state。

部署说明：
    - 两种模式互斥：ARTICLE_EXECUTION_MODE=worker 时不要再跑 inline API，
      否则同一任务可能被 API 后台协程与 worker 双重消费；
    - 心跳是段级粒度（一个节点可能跑数分钟），STALE_SECONDS 必须大于
      单节点最长耗时（默认 900s）；
    - 如需更大吞吐：多开几个 worker 进程即可，CAS 领取保证不重不漏；
      引入 Celery/Redis 队列属于后续扩展位（本次不实现）。
"""

from __future__ import annotations

from ..core.logger import logger

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid7

from . import service
from .dal import TaskDAO
from .graph.service import get_graph_service

_LOG_PREFIX = "[article-worker]"


def _log(message: str) -> None:
    logger.info(f"{_LOG_PREFIX} {message}")


def _iso_minus(seconds: int) -> str:
    """当前 UTC 时间减去 seconds 的 ISO 串（与 service._now() 同格式，可字典序比较）。"""
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(timespec="seconds")


class ArticleWorker:
    """常驻任务消费者：asyncio 主循环 + ThreadPoolExecutor 执行图段。"""

    def __init__(self, poll_interval: float | None = None,
                 concurrency: int | None = None,
                 stale_seconds: int | None = None) -> None:
        from ..core.config import get_settings

        settings = get_settings()
        self.poll_interval = float(
            poll_interval if poll_interval is not None
            else settings.ARTICLE_WORKER_POLL_INTERVAL)
        concurrency = int(
            concurrency if concurrency is not None
            else settings.ARTICLE_WORKER_CONCURRENCY)
        self.stale_seconds = int(
            stale_seconds if stale_seconds is not None
            else settings.ARTICLE_WORKER_STALE_SECONDS)
        # LangGraph / LLM 调用是同步 API：放线程池执行，事件循环只做 DB 编排
        self.concurrency = max(concurrency, 1)
        self.pool = ThreadPoolExecutor(
            max_workers=self.concurrency, thread_name_prefix="article-graph")
        self.worker_id = f"worker-{os.getpid()}-{str(uuid7())[:8]}"
        self._inflight: set[str] = set()

    # ------------------------------------------------------------------ #
    # 主循环
    # ------------------------------------------------------------------ #

    async def run_forever(self) -> None:
        """常驻主循环：扫描 -> 派发 -> 睡眠，直到进程被终止。"""
        _log(f"worker 启动：id={self.worker_id} 并发={self.concurrency} "
             f"轮询间隔={self.poll_interval}s 失联阈值={self.stale_seconds}s")
        while True:
            try:
                await self._scan_and_dispatch()
            except Exception as exc:
                # 单轮扫描失败不退出：下一轮重试（DB 瞬时抖动等）
                logger.error(f"{_LOG_PREFIX} 扫描轮次失败：{type(exc).__name__}: {exc}")
            await asyncio.sleep(self.poll_interval)

    async def _scan_and_dispatch(self) -> int:
        """领取并派发本轮可执行任务，返回派发数。

        inflight 上限即线程池大小：图段在线程池里排队没有意义，
        领了不跑反而占住 running 状态。
        """
        from ..core import session_scope

        async with session_scope() as session:
            rows = await TaskDAO(session).list_claimable(_iso_minus(self.stale_seconds))
        dispatched = 0
        for row in rows:
            if len(self._inflight) >= self.concurrency:
                break
            if row.task_id in self._inflight:
                continue
            self._inflight.add(row.task_id)
            asyncio.create_task(self._run_claimed(row.task_id, row.status),
                                name=f"article-worker-{row.task_id}")
            dispatched += 1
        if dispatched:
            _log(f"本轮派发 {dispatched} 个任务：inflight={sorted(self._inflight)}")
        return dispatched

    # ------------------------------------------------------------------ #
    # 单任务执行
    # ------------------------------------------------------------------ #

    async def _run_claimed(self, task_id: str, expect_status: str) -> None:
        """领取（CAS）并执行一个任务；任何异常都收敛到任务表，不让进程崩。"""
        from ..core import session_scope

        try:
            async with session_scope() as session:
                claimed = await TaskDAO(session).claim(
                    task_id, self.worker_id, service._now(), expect_status=expect_status)
            if not claimed:
                return  # 被其他 worker 抢先，直接放弃

            action, payload = await self._plan_task(task_id)
            if action == "fail":
                await service._fail_task(task_id, str(payload))
                return
            if action == "review":
                # 工作流停在未答复 interrupt 且没有审批决定：还原审批卡等前端
                thread_id = str(payload.pop("_thread_id", "") or "")
                await service._pause_for_review(
                    task_id, payload, thread_id,
                    str(payload.get("stage", "")) or "review",
                )
                return
            if action == "resume":
                # 先清掉决定字段再执行：崩溃在执行中也不会重复消费同一次审批
                await service._update_task(
                    task_id, review_decision="", review_suggest="",
                    thread_id=payload["thread_id"])
                await service.run_generation_segment(
                    task_id, payload["command"], executor=self.pool, serialize=False)
                return
            # continue / fresh：payload 就是 step_input
            await service.run_generation_segment(
                task_id, payload, executor=self.pool, serialize=False)
        except Exception as exc:
            logger.error(f"{_LOG_PREFIX} 任务 {task_id} 执行异常："
                         f"{type(exc).__name__}: {exc}")
            try:
                await service._fail_task(task_id, f"worker 执行异常: {type(exc).__name__}: {exc}")
            except Exception:
                pass
        finally:
            self._inflight.discard(task_id)

    async def _plan_task(self, task_id: str) -> tuple[str, object]:
        """按任务表现场规划下一段输入，返回 (action, payload)。

        action：
            resume    消费 API 记录的审批决定（payload={"thread_id","command"}）；
            review    还原审批卡（payload=interrupt dict，附 _thread_id）；
            continue  有 checkpoint 无 interrupt（payload=None，断点续跑）；
            fresh     从头跑首段（payload=initial state dict）；
            fail      任务无法继续（payload=失败原因）。
        """
        svc = get_graph_service()
        row = await service._get_task_snapshot(task_id)
        if row is None:
            return "fail", "任务记录丢失"

        thread_id = str(row.thread_id or "")
        decision = str(row.review_decision or "").strip()

        # 1) API 记录的审批决定：仅在确实停在 interrupt 时消费
        if decision and thread_id:
            has_cp = await service._has_checkpoint(thread_id, self.pool)
            interrupt = (await self._probe(svc.pending_interrupt, thread_id)) if has_cp else None
            if interrupt:
                command = svc.resume_command(decision, str(row.review_suggest or ""))
                return "resume", {"thread_id": thread_id, "command": command}
            # 决定已失效（状态不一致/崩溃残留）：清掉，走常规规划
            await service._update_task(task_id, review_decision="", review_suggest="")

        # 2) checkpoint 现场决定续跑方式
        if thread_id and await service._has_checkpoint(thread_id, self.pool):
            interrupt = await self._probe(svc.pending_interrupt, thread_id)
            if interrupt:
                value = dict(interrupt)
                value["_thread_id"] = thread_id
                return "review", value
            return "continue", None

        # 3) 无 checkpoint：从头跑首段（素材被清理则失败）
        material = await service.get_material_cached(row.event_id)
        if material is None:
            return "fail", "话题素材已被清理，无法继续生成"
        return "fresh", svc.initial_state(
            material.model_dump(), need_review=bool(row.need_review))

    async def _probe(self, fn, thread_id: str):
        """在工作线程池里执行同步探测（checkpoint/interrupt）。"""
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(self.pool, fn, thread_id)
        except Exception as exc:
            _log(f"探测 checkpoint 失败 thread={thread_id}：{type(exc).__name__}: {exc}")
            return None


# --------------------------------------------------------------------------- #
# 进程入口
# --------------------------------------------------------------------------- #

async def _amain() -> None:
    """worker 启动序列：建库/补列（幂等）-> 常驻循环。"""
    from ..core import database

    await database.init_db()
    await service.migrate_task_columns()
    await service.migrate_time_columns()
    await service.migrate_article_columns()
    worker = ArticleWorker()
    await worker.run_forever()


def main() -> int:
    """进程入口（python -m app.article.worker）。Ctrl-C 优雅退出。"""
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        _log("收到退出信号，worker 停止（进行中的段由心跳超时被下一个 worker 接管）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
