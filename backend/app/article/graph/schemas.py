"""graph 调试/编排接口的请求契约（Pydantic）。

这些接口面向前端 xyflow 画布与工作流调试，与文章业务接口
（/v1/articles/*，契约在 router.py 内联定义）解耦。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GraphStreamRequest(BaseModel):
    """POST /graph/stream：SSE 流式执行。

    两种模式二选一（都传/都不传返回 422）：
      - 新建任务：传 init_state（完整初始 state，来源 initial_state_from_material）；
      - 续跑/重放：传 checkpoint_id，从该快照继续执行（可传 resume 恢复 interrupt）。
    resume：interrupt 断点的恢复载荷（{"decision": "pass"} 等），可选。
    """

    thread_id: str = Field(min_length=1, description="检查点线程 id")
    init_state: dict[str, Any] | None = Field(
        default=None, description="新建任务：完整初始 state")
    checkpoint_id: str | None = Field(
        default=None, description="从指定快照续跑/重放；与 init_state 互斥")
    resume: Any | None = Field(
        default=None, description="interrupt 恢复载荷（Command(resume=...)），可选")


class GraphStateRequest(BaseModel):
    """POST /graph/state：读取指定 thread（可选 checkpoint）的状态快照。"""

    thread_id: str = Field(min_length=1)
    checkpoint_id: str | None = None


class GraphUpdateStateRequest(BaseModel):
    """POST /graph/update-state：人工审核专用，直接修改 state 字段。

    values：要写入的 state 字段（如 outline_review / modify_suggest）；
    as_node：可选，把更新归属到指定节点（省略时 LangGraph 自动判断，
    在 interrupt 断点上省略即可）。
    """

    thread_id: str = Field(min_length=1)
    checkpoint_id: str | None = None
    values: dict[str, Any] = Field(description="要更新的 state 字段")
    as_node: str | None = Field(
        default=None, description="更新归属节点；interrupt 断点上省略")


class GraphCheckpointItem(BaseModel):
    """GET /graph/checkpoints 的单条快照。"""

    checkpoint_id: str
    parent_checkpoint_id: str | None = None
    step: int = 0
    ts: str = ""
    source: str = ""


class GraphCheckpointsResponse(BaseModel):
    """GET /graph/checkpoints：某 thread 的全部快照（新的在前）。"""

    thread_id: str
    items: list[GraphCheckpointItem]
    total: int
