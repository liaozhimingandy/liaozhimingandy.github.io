"""工作流执行入口：分段驱动（HITL）与 CLI，从原 app/article/llm.py 原样迁移。

run_graph_step 是服务层/API 统一的分段执行入口：
    - 首次传完整 initial state，工作流跑到第一个 interrupt 暂停；
    - 暂停后把待审内容交给前端，用户决定后传 Command(resume=...) 续跑；
    - 传 None 表示「从最后 checkpoint 续跑」（瞬时故障/进程重启恢复）。

同步实现（LangGraph/LangChain 同步 API）：调用方（FastAPI 服务层）用
asyncio.to_thread 调入线程执行，不阻塞事件循环——这是「同步库不阻塞
async 服务」的标准做法，不是旧方案的手动开线程托管业务。

CLI 用法（包模块方式运行）：
    py -3.13 -m app.article.graph.runner --event-id 2 --auto-approve
    （旧的 python -m app.article.llm 入口保留，内部委托到这里）

异步任务队列扩展位（本次不实现）：如需把生成段放到独立 worker 执行，
可引入 Celery：service.run_generation_segment 里的 asyncio.create_task
替换为 task = celery_app.send_task("article.run_segment", args=[task_id,
step_input])，worker 侧直接调 run_graph_step；checkpoint 已持久化在
Postgres，worker 与 API 进程可共享断点，无需改动本模块。
"""

from ...core.logger import logger

import argparse
import asyncio
import json

from uuid import uuid7

from .builder import get_graph
from .config import LLM_MODEL
from .state import REVIEW_PASS, ArticleState


def run_graph_step(
    step_input: dict | None,
    thread_id: str,
) -> dict:
    """驱动工作流执行「一段」：直到遇到 HITL 断点或跑完。

    这是服务层/API 统一的分段执行入口，也是 HITL 部署的核心：
      - 首次调用传完整 initial state（dict），工作流跑到第一个 interrupt 暂停；
      - 暂停后调用方把待审内容展示给用户，用户决定后传
        ``Command(resume={"decision":..., "suggest":...})`` 再调用本函数；
      - 传 ``None`` 表示「从最后 checkpoint 续跑」：最后执行的节点没有
        落 checkpoint（执行中途失败/进程重启），重跑该节点即可从报错处
        继续，已完成节点不重复消耗 LLM 调用；
      - ``Command`` 对象由 :func:`resume_command` 构造，避免服务层依赖 langgraph 类型。

    返回结构（不含数据读写，由 service 层决定落库时机）：
        {"status": "paused", "state": {...}, "interrupt": {...}, "stage": "outline|final"}
        {"status": "done",   "state": {...}, "interrupt": None, "stage": ""}
        {"status": "error",  "state": {},    "interrupt": None, "error_msg": "..."}

    thread_id 必须每次运行唯一：否则命中旧 checkpoint 会带入上一次的
    outline/draft 污染输入。checkpointer 负责在暂停点持久化 state，
    因此进程重启后只要 checkpointer 是 Postgres，仍可用同一 thread_id 恢复。
    """
    from langgraph.types import Command  # 局部导入：模块级保持轻量

    config = {"configurable": {"thread_id": thread_id}}
    last_node = ""
    try:
        # dict=initial state / None=从 checkpoint 续跑 / Command=恢复审核——stream 均接受
        for chunk in get_graph().stream(step_input, config=config, stream_mode="updates"):
            for node_name, update in chunk.items():
                if node_name == "__interrupt__":
                    interrupts = list(update)
                    if not interrupts:
                        continue
                    it = interrupts[0]
                    value = it.value if hasattr(it, "value") else it
                    stage = value.get("stage", "") if isinstance(value, dict) else ""
                    logger.info(f"[llm] 工作流暂停等待审核：stage={stage} thread={thread_id}")
                    return {
                        "status": "paused",
                        "state": dict(_graph_state(config)),
                        "interrupt": value,
                        "stage": stage,
                        "last_node": last_node,
                    }
                last_node = node_name
                logger.info(f"\n👉 正在执行节点：【{node_name}】")
                logger.info(f"本次输出字段：{list(update.keys())}")
                logger.info("-" * 70)
    except Exception as exc:
        logger.error(f"❌ 工作流执行失败：{type(exc).__name__}: {exc}")
        return {"status": "error", "state": {}, "interrupt": None,
                "error_msg": f"{type(exc).__name__}: {exc}", "last_node": last_node}

    state = dict(_graph_state(config))
    if isinstance(step_input, Command):
        final_state = state
    elif state:
        final_state = state
    else:
        # 无 checkpoint 的一次性运行（理论上不会发生：图里有两个 interrupt）
        final_state = _build_initial_state(step_input or {})
    return {"status": "done", "state": final_state, "interrupt": None,
            "stage": "", "last_node": last_node}


def has_checkpoint(thread_id: str) -> bool:
    """thread 是否已有持久化 checkpoint（判断能否断点续跑）。

    进程重启后 service 层据此决定：有 checkpoint 从断点续跑（None 输入），
    没有（任务还是 queued，首段没跑过）则从头跑首段。
    """
    try:
        return bool(get_graph().get_state(
            {"configurable": {"thread_id": thread_id}}).values)
    except Exception:
        return False


def pending_interrupt(thread_id: str) -> dict | None:
    """checkpoint 是否停在一个未答复的 interrupt（HITL 暂停点）。

    进程可能在「工作流已暂停等审核」与「任务状态写库」之间被杀，
    重启恢复时据此把任务还原成 waiting_approval，而不是错误地续跑。
    返回 interrupt 的 value dict（含 stage/title/content/options）。
    """
    try:
        state = get_graph().get_state({"configurable": {"thread_id": thread_id}})
        for task in getattr(state, "tasks", ()) or ():
            for it in getattr(task, "interrupts", ()) or ():
                value = it.value if hasattr(it, "value") else it
                if isinstance(value, dict):
                    return value
    except Exception:
        pass
    return None


def _graph_state(config: dict) -> dict:
    """读取当前 checkpoint 的 state；空则返回空 dict。"""
    try:
        return get_graph().get_state(config).values or {}
    except Exception:
        return {}


def resume_command(decision: str, suggest: str = "") -> object:
    """构造交给 run_graph_step 的 resume 输入（封装 Command，隔离 langgraph 依赖）。"""
    from langgraph.types import Command

    return Command(resume={"decision": decision, "suggest": suggest})


def _build_initial_state(pick: dict) -> ArticleState:
    """正文素材来自 DAL get_event_material()，已关联 news 表取好并截断。"""
    return {
        "event_title": pick.get("event_title") or "",
        "event_summary": pick.get("event_summary") or "",
        "source_contents": pick.get("source_contents") or [],
        "source_urls": pick.get("source_urls") or [],
        "need_review": bool(pick.get("need_review", True)),
        "outline": "",
        "outline_review": "",
        "modify_suggest": "",
        "draft": "",
        "multi_platform": {},
        "check_report": "",
        "final_review": "",
        "final_article": "",
    }


def initial_state_from_material(material: dict, need_review: bool = True) -> dict:
    """由素材组装工作流初始 state（服务端分段执行的起点）。

    need_review 控制该次生成是否在大纲/终审断点暂停等人工审核；
    服务层按「请求参数优先，否则读 ARTICLE_HITL_ENABLED 配置」解析后传入。
    """
    state = _build_initial_state(material)
    state["need_review"] = bool(need_review)
    return state


# --------------------------------------------------------------------------- #
# CLI 兼容入口（原 run_one 语义：自动通过所有断点跑完）
# --------------------------------------------------------------------------- #

def run_one(material: dict, thread_id: str, auto_approve: bool = True) -> dict:
    """CLI 兼容入口：跑完整工作流并自动通过所有断点，返回最终 state。

    服务端 HITL 不走这里——改用 run_graph_step/resume_command 分段驱动，
    让前端能在审核点介入。material 为 DAL get_event_material() 的 model_dump()。
    """
    event_id = int(material["id"])
    logger.info(f"\n===== 开始流水线：event={event_id} thread={thread_id} "
          f"{material.get('event_title')} =====")
    final_state = _run_one_auto(material, thread_id)
    if not final_state:
        return {}
    _print_final(final_state)
    return final_state


def _run_one_auto(pick: dict, thread_id: str) -> dict:
    """CLI 兼容：自动通过所有断点，跑到结束（原 run_one 语义）。"""
    event_id = int(pick["id"])
    step_input = _build_initial_state(pick)
    seen = 0
    while True:
        result = run_graph_step(step_input, thread_id)
        if result["status"] == "done":
            return result["state"]
        if result["status"] == "error":
            logger.error(f"❌ 事件 {event_id} 生成失败：{result.get('error_msg')}")
            return {}
        # paused：CLI 无前端，自动通过
        seen += 1
        if seen > 10:  # 防止异常循环导致死循环
            logger.error(f"❌ 事件 {event_id} 审核循环超过 10 次，中止")
            return {}
        step_input = resume_command(REVIEW_PASS)


def _print_final(state: dict):
    """打印最终产出：定稿 + 多平台版本。"""
    logger.info("\n===== 🎉 流水线执行完毕 =====")
    logger.info("【定稿文章 final_article】")
    logger.info(state.get("final_article", ""))
    logger.info("\n📱 多平台版本：")
    logger.info(json.dumps(state.get("multi_platform") or {}, ensure_ascii=False, indent=2))


async def _cli_main(args) -> None:
    """CLI：重跑指定事件。走 SQLModel 自动建表（postgres/内存按环境配置）。"""
    from ...core import database, session_scope
    from ..service import ArticleService

    await database.init_db()
    async with session_scope() as session:
        material = await ArticleService(session).get_material(args.event_id)
        if material is None:
            logger.error(f"❌ 指定事件不存在：event={args.event_id}")
            return
        run_id = str(uuid7())
        thread_id = f"event_{material.id}_{run_id}"
        state = run_one(material.model_dump(), thread_id, auto_approve=args.auto_approve)
        if not state:
            return
        # CLI 直接落库（与 service._finalize_done 相同的持久化语义）
        status = "done" if state.get("final_review") == "pass" else "review"
        article_id = await ArticleService(session).save_generation_result(
            material, thread_id,
            article_uuid=str(uuid7()),
            state=state, model_name=LLM_MODEL,
        )
    logger.info(f"[llm] 已落库：article={article_id}, event={args.event_id} -> {status}")


def cli(argv=None) -> int:
    """CLI 入口（python -m app.article.graph.runner）。"""
    parser = argparse.ArgumentParser(description="重跑指定事件的生成工作流")
    parser.add_argument("--event-id", type=int, required=True,
                        help="要重跑的事件 id（旧文章保留为历史版本）")
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="自动通过大纲审核与终审，适合批量/非交互运行",
    )
    asyncio.run(_cli_main(parser.parse_args(argv)))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
