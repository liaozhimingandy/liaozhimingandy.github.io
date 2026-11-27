"""自媒体热点流水线的两阶段编排入口。

阶段职责保持独立：
    1. collector 采集热点新闻并入库（collector.py）
    2. cluster   把 pending topic 聚合成 event（cluster.py）

本文件只做顺序调用、日志和入口参数，不包含采集/聚类业务逻辑。
数据会话由 collector / cluster 内部通过 session_scope 自管，
本层不持有数据库会话；数据库初始化用 core.database.init_db()
（SQLModel 自动建表，无需手写 DDL）。

用法（包模块方式运行）：
    py -3.13 -m app.article.pipeline --stage all       # 先采集，再聚合（默认）
    py -3.13 -m app.article.pipeline --stage collect   # 只采集
    py -3.13 -m app.article.pipeline --stage cluster   # 只聚合
"""

from ..core.logger import logger

import argparse
import asyncio
import time

from ..core import database
from . import cluster, collector

STAGE_COLLECT = "collect"
STAGE_CLUSTER = "cluster"
STAGE_ALL = "all"


def _stage_banner(name: str):
    logger.info("\n" + "=" * 60)
    logger.info(f"阶段：{name}")
    logger.info("=" * 60)


async def run_collect() -> dict:
    """执行采集阶段，返回本次采集统计。"""
    _stage_banner("采集热点新闻")
    started = time.time()
    stats = await collector.run_collect()
    logger.info(f"[pipeline] 采集完成：{stats} | 耗时 {time.time() - started:.1f}s")
    return stats


async def run_cluster() -> None:
    """执行聚合阶段；只做一次扫描，不写轮询。"""
    _stage_banner("聚合事件")
    started = time.time()
    await cluster.cluster_new_topics()
    logger.info(f"[pipeline] 聚合完成 | 耗时 {time.time() - started:.1f}s")


async def _main_async(argv=None) -> int:
    parser = argparse.ArgumentParser(description="自媒体热点采集流水线")
    parser.add_argument(
        "--stage",
        choices=(STAGE_COLLECT, STAGE_CLUSTER, STAGE_ALL),
        default=STAGE_ALL,
        help="要执行的阶段：all=先采集再聚合（默认）",
    )
    args = parser.parse_args(argv)

    if not await database.init_db():
        logger.info("[pipeline] 数据库不可用，已降级内存库（数据不落盘）")
    started = time.time()
    if args.stage in (STAGE_COLLECT, STAGE_ALL):
        await run_collect()
    if args.stage in (STAGE_CLUSTER, STAGE_ALL):
        await run_cluster()
    await database.dispose_engine()
    logger.info(f"[pipeline] 本次运行结束（stage={args.stage}），总耗时 {time.time() - started:.1f}s")
    return 0


def main(argv=None) -> int:
    """同步 CLI 入口（供脚本调用）；自身运行时走 asyncio.run。"""
    return asyncio.run(_main_async(argv))


if __name__ == "__main__":
    raise SystemExit(main())
