"""graph 调试/编排 REST API（SSE 流式 + 状态/快照/图结构）。

与文章业务接口（/v1/articles/*，任务语义在 service 层）解耦：
    - /graph/stream        SSE 流式执行（stream_mode="updates"），
                           事件：node_update / finish / error
    - /graph/state         读指定 thread/checkpoint 的 state（values + next，
                           next 非空即停在了 interrupt 断点）
    - /graph/update-state  人工审核专用：直接改 state 字段（大纲 pass/reject、
                           修改意见）；生产审核主链路仍是
                           POST /v1/articles/tasks/{id}/review（Command(resume)）
    - /graph/checkpoints   某 thread 的全部快照列表（前端 xyflow 画布）
    - /graph/graph-schema  graph.to_json()，前端渲染 DAG 流程图

⚠️ 并发约束：同一个 thread_id 不能同时发起多次 stream——两次并发 stream
会交错写同一 checkpoint 链，state 互相污染。本路由用进程内 _ACTIVE_STREAMS
做了软防护（409）；sqlite checkpointer 有文件锁，多进程并发写会报
database is locked，生产必须 PostgresSaver（saver.py 按 DSN 自动切换）。

SSE 异常语义：流内任何异常都会捕获并推送 error 事件，不让连接悬死。
"""

from __future__ import annotations

import json
import threading
from typing import Any, Iterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from ...core.database import get_session
from ...portal.router import _api_error, require_principal
from . import builder, runner, saver
from .schemas import (
    GraphCheckpointsResponse,
    GraphCheckpointItem,
    GraphStateRequest,
    GraphStreamRequest,
    GraphUpdateStateRequest,
)

router = APIRouter()

# 进程内 stream 防重入：同一 thread_id 同时只允许一条 SSE 流（软防护，
# 多实例部署需 DB 层或队列层兜底）。finish/error 时释放。
_ACTIVE_STREAMS: set[str] = set()
_STREAMS_LOCK = threading.Lock()


def _sse(event: str, data: Any) -> str:
    """格式化一条 SSE 事件（event + data 两行，空行结尾）。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _snapshot_public(snapshot) -> dict[str, Any]:
    """StateSnapshot -> 公共视图：values / next / tasks（interrupt 摘要）。"""
    tasks = []
    for task in getattr(snapshot, "tasks", ()) or ():
        interrupts = []
        for it in getattr(task, "interrupts", ()) or ():
            value = it.value if hasattr(it, "value") else it
            interrupts.append(value if isinstance(value, dict) else {"value": value})
        tasks.append({
            "id": str(getattr(task, "id", "") or ""),
            "name": str(getattr(task, "name", "") or ""),
            "error": str(getattr(task, "error", "") or ""),
            "interrupts": interrupts,
        })
    checkpoint_id = (snapshot.config or {}).get("configurable", {}).get("checkpoint_id", "")
    return {
        "values": snapshot.values or {},
        "next": list(getattr(snapshot, "next", ()) or ()),
        "checkpoint_id": checkpoint_id,
        "tasks": tasks,
        # next 非空且 tasks 带 interrupts => 正停在人工审核断点
        "waiting_interrupt": any(t["interrupts"] for t in tasks),
    }


@router.post("/graph/stream", tags=["graph"])
async def graph_stream(
    body: GraphStreamRequest,
    principal: Any = Depends(require_principal),
) -> StreamingResponse:
    """SSE 流式执行工作流（stream_mode="updates"）。

    事件序列：若干 node_update -> finish（含最终 values 与停点）；
    流内任何异常推送 error 事件后结束。
    """
    if body.init_state and body.checkpoint_id:
        raise _api_error(422, "INVALID_STREAM_MODE",
                         "init_state 与 checkpoint_id 互斥：新建任务传 init_state，续跑传 checkpoint_id")
    if not body.init_state and not body.checkpoint_id and body.resume is None:
        raise _api_error(422, "INVALID_STREAM_MODE",
                         "缺少输入：新建任务传 init_state；续跑/重放传 checkpoint_id")

    with _STREAMS_LOCK:
        if body.thread_id in _ACTIVE_STREAMS:
            raise _api_error(409, "THREAD_STREAMING",
                             f"thread {body.thread_id} 已有流在执行，同一 thread 不能并发 stream")
        _ACTIVE_STREAMS.add(body.thread_id)

    config: dict = {"configurable": {"thread_id": body.thread_id}}
    if body.checkpoint_id:
        config["configurable"]["checkpoint_id"] = body.checkpoint_id

    # 输入优先级：resume（恢复 interrupt）> checkpoint_id（从快照续跑，input=None）
    # > init_state（新建任务）
    if body.resume is not None:
        from langgraph.types import Command

        step_input: Any = Command(resume=body.resume)
    elif body.init_state is not None:
        step_input = body.init_state
    else:
        step_input = None

    compiled = builder.get_graph()

    def _gen() -> Iterator[str]:
        try:
            for chunk in compiled.stream(step_input, config=config, stream_mode="updates"):
                for node_name, update in chunk.items():
                    if node_name == "__interrupt__":
                        interrupts = list(update) if isinstance(update, (list, tuple)) else [update]
                        payload = []
                        for it in interrupts:
                            value = getattr(it, "value", it)
                            payload.append(value if isinstance(value, dict) else {"value": value})
                        # interrupt 也按 node_update 事件推送：node=__interrupt__，
                        # 前端据此渲染审批卡并等待用户决定
                        yield _sse("node_update", {"node": "__interrupt__",
                                                   "update": {"interrupts": payload}})
                        continue
                    yield _sse("node_update", {"node": node_name, "update": update})
            # finish 用 thread 最新状态（config 带 checkpoint_id 时查的是历史快照）
            snapshot = compiled.get_state(
                {"configurable": {"thread_id": body.thread_id}})
            yield _sse("finish", {
                "thread_id": body.thread_id,
                "values": snapshot.values or {},
                "next": list(getattr(snapshot, "next", ()) or ()),
            })
        except Exception as exc:
            # 任何异常都以 error 事件收尾，不让前端连接悬死
            yield _sse("error", {
                "thread_id": body.thread_id,
                "message": f"{type(exc).__name__}: {exc}",
            })
        finally:
            with _STREAMS_LOCK:
                _ACTIVE_STREAMS.discard(body.thread_id)

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/graph/state", tags=["graph"])
async def graph_state(
    body: GraphStateRequest,
    principal: Any = Depends(require_principal),
) -> dict[str, Any]:
    """读取指定 thread（可选 checkpoint）的状态：values / next / tasks。"""
    config: dict = {"configurable": {"thread_id": body.thread_id}}
    if body.checkpoint_id:
        config["configurable"]["checkpoint_id"] = body.checkpoint_id
    try:
        snapshot = builder.get_graph().get_state(config)
    except Exception as exc:
        raise _api_error(500, "GRAPH_STATE_ERROR",
                         f"读取状态失败：{type(exc).__name__}: {exc}") from None
    if not snapshot.values and not list(getattr(snapshot, "next", ()) or ()):
        # 空 values + 空 next = thread 还没有任何 checkpoint（如未知 thread）
        raise _api_error(404, "THREAD_NOT_FOUND", f"thread 无状态：{body.thread_id}")
    return _snapshot_public(snapshot)


@router.post("/graph/update-state", tags=["graph"])
async def graph_update_state(
    body: GraphUpdateStateRequest,
    principal: Any = Depends(require_principal),
) -> dict[str, Any]:
    """人工审核专用：直接修改 state 字段（大纲 pass/reject、修改意见等）。

    典型用法：工作流停在 human_review_outline 断点时，前端提交
    {"values": {"outline_review": "pass"}}（或填 modify_suggest），
    随后 /graph/stream 传 checkpoint_id 续跑。生产审核主链路走
    POST /v1/articles/tasks/{id}/review（Command(resume)），本接口
    主要面向 xyflow 画布调试与人工兜底干预。
    """
    config: dict = {"configurable": {"thread_id": body.thread_id}}
    if body.checkpoint_id:
        config["configurable"]["checkpoint_id"] = body.checkpoint_id
    try:
        compiled = builder.get_graph()
        compiled.update_state(config, values=body.values, as_node=body.as_node)
        snapshot = compiled.get_state(config)
    except Exception as exc:
        raise _api_error(500, "GRAPH_UPDATE_ERROR",
                         f"更新状态失败：{type(exc).__name__}: {exc}") from None
    return _snapshot_public(snapshot)


@router.get("/graph/checkpoints", tags=["graph"])
async def graph_checkpoints(
    thread_id: str = Query(min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    principal: Any = Depends(require_principal),
) -> dict[str, Any]:
    """列出某 thread 的全部快照（新的在前），供前端 xyflow 画布回放。"""
    items: list[GraphCheckpointItem] = []
    try:
        config = {"configurable": {"thread_id": thread_id}}
        for tp in saver.get_checkpointer().list(config, limit=limit):
            cp = tp.checkpoint or {}
            get = cp.get if isinstance(cp, dict) else (lambda k, d=None: getattr(cp, k, d))
            cp_id = (tp.config or {}).get("configurable", {}).get("checkpoint_id") \
                or get("id", "")
            parent_id = ""
            if tp.parent_config:
                parent_id = tp.parent_config.get("configurable", {}).get("checkpoint_id", "")
            items.append(GraphCheckpointItem(
                checkpoint_id=str(cp_id or ""),
                parent_checkpoint_id=str(parent_id) or None,
                step=int(get("step", 0) or 0),
                ts=str(get("ts", "") or ""),
                source=str((tp.metadata or {}).get("source", "")),
            ))
    except Exception as exc:
        raise _api_error(500, "CHECKPOINT_LIST_ERROR",
                         f"读取快照列表失败：{type(exc).__name__}: {exc}") from None
    # checkpointer.list 本身新在前，这里保序返回
    payload = GraphCheckpointsResponse(
        thread_id=thread_id, items=items, total=len(items))
    return payload.model_dump()


@router.get("/graph/graph-schema", tags=["graph"])
async def graph_schema(
    principal: Any = Depends(require_principal),
) -> dict[str, Any]:
    """返回工作流 DAG 结构（graph.get_graph().to_json()），前端渲染流程图。"""
    try:
        schema = builder.get_graph().get_graph().to_json()
    except Exception as exc:
        raise _api_error(500, "GRAPH_SCHEMA_ERROR",
                         f"生成图结构失败：{type(exc).__name__}: {exc}") from None
    return {"schema": schema}
