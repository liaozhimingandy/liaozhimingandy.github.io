"""独立运行入口：不启动 FastAPI，直接执行文章生成工作流。

用法：
    python standalone/run_workflow.py --event-id 2 --auto-approve
    python standalone/run_workflow.py --list            # 只列出可选话题
    python standalone/run_workflow.py --event-id 2      # HITL 断点由 CLI 逐个应答

也可以在其他 Python 项目里 import 调用（同一份 Graph、同一个 Service）：
    from app.article.graph.service import get_graph_service
    svc = get_graph_service()
    state = svc.run(material_dict, thread_id="my-thread-1")

本脚本不依赖 FastAPI：只 import app.article.graph.*（workflow/service/config
层）与 core.database（SQLModel，非 Web 依赖）。

执行结果落库走 service 层的 save_generation_result（与 FastAPI 模式、
worker 模式完全一致），同一 event 的旧文章自动转为历史版本。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import uuid7

# 保证以任意工作目录启动都能找到 backend 包（本文件位于 backend/standalone/）
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.article.graph.config import LLM_MODEL  # noqa: E402
from app.article.graph.service import get_graph_service  # noqa: E402


async def _list_topics() -> int:
    """列出可选择的话题（event），供 --event-id 取值参考。"""
    from app.core import database
    from app.article.service import ArticleService

    await database.init_db()
    async with database.session_scope() as session:
        events = await ArticleService(session).list_all_topics(limit=50)
    if not events:
        print("（暂无可选话题，请先运行采集与聚合：python -m app.article.pipeline --stage all）")
        return 0
    print(f"可选话题（event id -> 标题）：")
    for ev in events:
        print(f"  {ev.id:>6}  {ev.event_title}  [status={ev.status}]")
    return 0


async def _run(event_id: int, auto_approve: bool) -> int:
    """独立执行工作流：初始化 -> 组素材 -> GraphService.run -> 落库。"""
    from app.core import database
    from app.article import service as article_service
    from app.article.service import ArticleService

    # ---- 依赖初始化（独立模式的 lifespan 等价物：建库/补列，进程退出即释放） ----
    await database.init_db()
    await article_service.migrate_task_columns()
    await article_service.migrate_time_columns()

    # ---- 组素材（与 FastAPI 模式同一 service 层） ----
    async with database.session_scope() as session:
        material = await ArticleService(session).get_material(event_id)
    if material is None:
        print(f"❌ 事件不存在：event={event_id}（用 --list 查看可选话题）")
        return 1

    # ---- 执行（统一走 GraphService，与 FastAPI/worker 完全同一份图） ----
    svc = get_graph_service()
    thread_id = f"event_{event_id}_{uuid7()}"
    print(f"▶ 开始生成：event={event_id}《{material.event_title}》")
    print(f"  thread_id={thread_id}  model={LLM_MODEL}  auto_approve={auto_approve}")
    state = svc.run(material.model_dump(), thread_id, auto_approve=auto_approve)
    if not state:
        print("❌ 生成失败（详见 logs/ 错误日志）")
        return 1

    # ---- 结果处理：落库（与 FastAPI 模式同一持久化语义） ----
    async with database.session_scope() as session:
        article_id = await ArticleService(session).save_generation_result(
            material, thread_id, article_uuid=str(uuid7()),
            state=state, model_name=LLM_MODEL,
        )

    print("\n===== 🎉 生成完成 =====")
    print(f"article_id={article_id}  status="
          f"{'done' if state.get('final_review') == 'pass' else 'review'}")
    print("\n【定稿 final_article】")
    print(state.get("final_article", ""))
    print("\n【多平台版本】", ", ".join((state.get("multi_platform") or {}).keys()))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="独立运行文章生成工作流（不启动 FastAPI）")
    parser.add_argument("--event-id", type=int, help="要生成文章的事件 id")
    parser.add_argument("--list", action="store_true", help="列出可选话题后退出")
    parser.add_argument("--auto-approve", action="store_true",
                        help="自动通过大纲审核与终审（默认逐个在终端应答）")
    args = parser.parse_args(argv)

    if args.list:
        return asyncio.run(_list_topics())
    if args.event_id is None:
        parser.print_help()
        return 2
    try:
        return asyncio.run(_run(args.event_id, auto_approve=args.auto_approve))
    except KeyboardInterrupt:
        print("\n（已中断；已完成的节点 checkpoint 已持久化，可用相同 thread 续跑）")
        return 130
    except Exception as exc:  # CLI 错误输出：不走 HTTP 异常，直接打印退出码
        print(f"❌ 执行异常：{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
