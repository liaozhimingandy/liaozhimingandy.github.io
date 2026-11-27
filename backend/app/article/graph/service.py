"""GraphService：LangGraph 工作流的统一门面（双调用入口共用）。

定位（分层）：
    graph/runner.py   —— LangGraph 原语（分段执行/探测/CLI），不感知调用方；
    graph/service.py  —— 本模块：把原语包装成面向业务的服务接口，全局单例；
    service.py        —— FastAPI 进程内的任务编排引擎（inline 模式）调用它；
    worker.py         —— 独立常驻 worker 进程（worker 模式）在线程池里调用它。

设计要点：
    - 方法全部是**同步**方法（LangGraph/LangChain 同步 API）：调用方负责
      把调用放进线程（asyncio.to_thread / ThreadPoolExecutor），不阻塞事件循环；
    - 参数自包含：调用方只传 ``step_input`` / ``thread_id`` / 素材 dict，
      不依赖任何请求上下文——路由层与 worker 线程传同样的参数即可；
    - 委托到 runner 模块的**属性**（每次调用时解析），测试 patch
      ``app.article.graph.runner.run_graph_step`` 等仍然生效；
    - 单例在首次 ``get_graph_service()`` 时创建，graph 的 compile 只发生一次
      （见 builder.get_graph），API 进程与 worker 进程各持有一个进程级实例。
"""

from __future__ import annotations

from . import runner as _runner


class GraphService:
    """LangGraph 工作流服务门面：路由层与 worker 线程池的统一执行接口。"""

    @property
    def model(self) -> str:
        """当前生成模型名（落库到 article.model 用）。"""
        return _runner.LLM_MODEL

    # ---- 执行 ----

    def run_step(self, step_input: dict | object | None, thread_id: str) -> dict:
        """驱动工作流执行一段，返回
        {"status": "paused|done|error", "state", "interrupt", "stage", "last_node"}。

        step_input 三种形态（与 runner.run_graph_step 一致）：
            dict     首次运行的完整 initial state；
            Command  人工审批后的恢复指令（resume_command 构造）；
            None     从最后 checkpoint 续跑（瞬时故障/进程重启恢复）。
        """
        return _runner.run_graph_step(step_input, thread_id)

    def resume_command(self, decision: str, suggest: str = "") -> object:
        """构造审批恢复指令（封装 langgraph Command，隔离依赖）。"""
        return _runner.resume_command(decision, suggest)

    def initial_state(self, material: dict, need_review: bool = True) -> dict:
        """由素材 dict（EventMaterial.model_dump()）组装工作流初始 state。"""
        return _runner.initial_state_from_material(material, need_review=need_review)

    def run(self, material: dict, thread_id: str, auto_approve: bool = True) -> dict:
        """一键跑完整工作流并返回最终 state（独立运行/脚本调试的便捷入口）。

        与分段接口（run_step + resume_command）使用**同一份图与同一套执行
        逻辑**，区别仅是断点处理策略：auto_approve=True 时自动通过全部
        HITL 审核（CLI/批量场景）；需要人工介入时改用 run_step 分段驱动。

        返回最终 state dict（含 final_article / multi_platform）；
        失败返回空 dict（错误已记日志）。同步接口：本工作流是有界同步
        编排（httpx 同步客户端），独立脚本直接调用即可，无需 asyncio。
        """
        return _runner.run_one(material, thread_id, auto_approve=auto_approve)

    # ---- 探测（worker/API 判断任务下一步动作用） ----

    def has_checkpoint(self, thread_id: str) -> bool:
        """thread 是否已有持久化 checkpoint（能否断点续跑）。"""
        return _runner.has_checkpoint(thread_id)

    def pending_interrupt(self, thread_id: str) -> dict | None:
        """checkpoint 是否停在未答复的 interrupt（HITL 暂停点），返回其 value dict。"""
        return _runner.pending_interrupt(thread_id)


# 进程级单例：compile 只发生一次；API 进程与 worker 进程各持有一个实例。
_GRAPH_SERVICE: GraphService | None = None


def get_graph_service() -> GraphService:
    """取 GraphService 单例（懒初始化，进程内唯一）。"""
    global _GRAPH_SERVICE
    if _GRAPH_SERVICE is None:
        _GRAPH_SERVICE = GraphService()
    return _GRAPH_SERVICE
