"""article 流水线后台调度器：采集与聚合两个 asyncio 周期任务。

分层：跑在 FastAPI 事件循环上（不再是守护线程）；采集/聚合本身是协程
（collector.run_collect / cluster.cluster_new_topics），内部把阻塞操作
包进 asyncio.to_thread，因此调度器只需 asyncio 原语。

职责：
    1. 采集任务  每 ARTICLE_COLLECT_INTERVAL_MINUTES 分钟执行一次
                 collector.run_collect()（抓热点 -> 搜新闻 -> 入库）；
    2. 聚合任务  每 ARTICLE_CLUSTER_INTERVAL_MINUTES 分钟执行一次
                 cluster.cluster_new_topics()（pending topic 合并成 event）；
    3. 手动触发  run_collect_now() / run_cluster_now() 供管理接口调用，
                 与定时任务共用同一把 asyncio.Lock，避免同一阶段并发重叠。

生命周期：由 app.main 的 lifespan await start()/stop()；
stop() 取消任务并等待正在执行的一轮结束，不做强杀。

配置（环境变量，均有默认值）：
    ARTICLE_SCHEDULER_ENABLED          1/0，默认 1（FastAPI 启动即开启调度）
    ARTICLE_COLLECT_INTERVAL_MINUTES   采集间隔，默认 30
    ARTICLE_CLUSTER_INTERVAL_MINUTES   聚合间隔，默认 10
    ARTICLE_SCHEDULER_START_DELAY_SEC  启动后首次执行延迟，默认 60
    间隔设为 0 等价于关闭该阶段的定时执行（手动触发仍可用）。
"""

from __future__ import annotations

import asyncio
import time

from .. import config
from ..core import session_scope
from . import cluster, collector
from .dal import TopicDAO

# 每阶段一把执行锁：定时任务与手动触发互斥，同一阶段不重叠
_COLLECT_LOCK = asyncio.Lock()
_CLUSTER_LOCK = asyncio.Lock()

_stop_event: asyncio.Event | None = None
_tasks: list[asyncio.Task] = []

_LAST_COLLECT: dict = {"finished_at": None, "ok": None, "stats": None}
_LAST_CLUSTER: dict = {"finished_at": None, "ok": None}


def _log(message: str) -> None:
    print(f"[article-scheduler] {message}")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


async def run_collect_now() -> dict:
    """手动/定时共用的采集入口；返回采集统计。"""
    if _COLLECT_LOCK.locked():
        raise RuntimeError("collect_busy")
    async with _COLLECT_LOCK:
        started = time.time()
        try:
            stats = await collector.run_collect()
            _LAST_COLLECT.update(finished_at=_now(), ok=True, stats=stats)
            _log(f"采集完成：{stats} | 耗时 {time.time() - started:.1f}s")
            return stats
        except Exception as exc:
            _LAST_COLLECT.update(
                finished_at=_now(), ok=False,
                stats={"error": f"{type(exc).__name__}: {exc}"},
            )
            _log(f"采集失败：{type(exc).__name__}: {exc}")
            raise


async def run_cluster_now() -> int:
    """手动/定时共用的聚合入口；返回本次处理的 pending topic 数量。"""
    if _CLUSTER_LOCK.locked():
        raise RuntimeError("cluster_busy")
    async with _CLUSTER_LOCK:
        started = time.time()
        try:
            async with session_scope() as session:
                pending = await TopicDAO(session).count_pending()
            await cluster.cluster_new_topics()
            _LAST_CLUSTER.update(finished_at=_now(), ok=True)
            _log(f"聚合完成（pending={pending}）| 耗时 {time.time() - started:.1f}s")
            return pending
        except Exception as exc:
            _LAST_CLUSTER.update(finished_at=_now(), ok=False)
            _log(f"聚合失败：{type(exc).__name__}: {exc}")
            raise


async def _loop(stage: str, interval_seconds: float) -> None:
    """单阶段循环：先等启动延迟，再按固定间隔执行，stop 可随时打断。"""
    label = "采集" if stage == "collect" else "聚合"
    delay = config.article_scheduler_start_delay_sec()
    if delay > 0 and _stop_event is not None:
        _log(f"{label}任务就绪，{delay}s 后开始首轮（间隔 {interval_seconds:.0f}s）")
        if await _stop_event.wait():
            return
    while _stop_event is not None and not _stop_event.is_set():
        try:
            if stage == "collect":
                await run_collect_now()
            else:
                await run_cluster_now()
        except RuntimeError as exc:
            # 执行锁被占用（手动触发正在进行）——跳过本轮即可
            _log(f"{label}跳过本轮（{exc}）")
        except Exception:
            pass  # 异常已在 run_*_now 记录，循环继续
        if _stop_event is not None and await _stop_event.wait(interval_seconds):
            return


async def start() -> dict:
    """启动采集/聚合周期任务；重复调用安全（已启动则直接返回状态）。

    必须在事件循环内调用（lifespan），且 DAL 需已初始化。
    """
    global _stop_event, _tasks
    if _tasks and any(not t.done() for t in _tasks):
        return status()

    _stop_event = asyncio.Event()
    _stop_event.clear()
    tasks: list[asyncio.Task] = []

    collect_interval = config.article_collect_interval_minutes() * 60
    cluster_interval = config.article_cluster_interval_minutes() * 60

    if collect_interval > 0:
        tasks.append(asyncio.create_task(
            _loop("collect", collect_interval), name="article-collector"))
        _log(f"采集任务已启动（间隔 {config.article_collect_interval_minutes()} 分钟）")
    else:
        _log("采集定时执行已关闭（ARTICLE_COLLECT_INTERVAL_MINUTES=0）")

    if cluster_interval > 0:
        tasks.append(asyncio.create_task(
            _loop("cluster", cluster_interval), name="article-cluster"))
        _log(f"聚合任务已启动（间隔 {config.article_cluster_interval_minutes()} 分钟）")
    else:
        _log("聚合定时执行已关闭（ARTICLE_CLUSTER_INTERVAL_MINUTES=0）")

    _tasks = tasks
    return status()


async def stop() -> None:
    """取消周期任务并等待当前一轮执行结束（由协程自身让出控制权保证）。"""
    global _stop_event, _tasks
    if _stop_event is not None:
        _stop_event.set()
    current = [t for t in _tasks if not t.done()]
    _tasks = []
    if current:
        await asyncio.gather(*current, return_exceptions=True)
    _stop_event = None


def status() -> dict:
    """调度器运行状态：任务存活、间隔配置、最近一次执行结果。"""
    return {
        "enabled": config.article_scheduler_enabled(),
        "tasks": {
            "collect": bool(_tasks) and not _tasks[0].done() if _tasks else False,
            "cluster": len(_tasks) > 1 and not _tasks[1].done(),
        },
        "interval_minutes": {
            "collect": config.article_collect_interval_minutes(),
            "cluster": config.article_cluster_interval_minutes(),
        },
        "last_collect": dict(_LAST_COLLECT),
        "last_cluster": dict(_LAST_CLUSTER),
    }
