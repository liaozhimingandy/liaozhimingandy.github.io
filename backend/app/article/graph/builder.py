"""工作流图装配：StateGraph 组装 + 编译单例。

⚠️ 并发约束（重要）：
    1. graph 全局单例：compile() 只执行一次（首次 get_graph() 时编译并缓存），
       绝不能在接口/线程里反复编译——每次 compile 都会重建整个图与节点绑定。
    2. 同一个 thread_id 不能同时发起多次 stream：两次并发 stream 会交错写
       同一条 checkpoint 链，state 会互相污染。sqlite checkpointer 还有文件锁
       问题（多进程并发写同一库文件会报 database is locked），生产必须切换
       PostgresSaver（本包 saver.py 已预留切换位置：配置 database_dsn 即生效）。
       跨进程的全局串行需外部队列（Celery）——见 runner.py 尾部注释。
"""

from langgraph.graph import END, StateGraph

from .nodes import (
    auto_check,
    generate_draft,
    generate_multi_platform,
    generate_outline,
    human_final_review,
    human_review_outline,
    re_generate_outline,
    route_outline,
)
from .saver import get_checkpointer
from .state import ArticleState

_GRAPH = None


def _build_graph():
    """组装并编译工作流图（7 节点 + 2 个 HITL interrupt 断点）。"""
    builder = StateGraph(ArticleState)
    for name, fn in (
        ("generate_outline", generate_outline),
        ("human_review_outline", human_review_outline),
        ("re_generate_outline", re_generate_outline),
        ("generate_draft", generate_draft),
        ("generate_multi_platform", generate_multi_platform),
        ("auto_check", auto_check),
        ("human_final_review", human_final_review),
    ):
        builder.add_node(name, fn)

    builder.set_entry_point("generate_outline")
    builder.add_edge("generate_outline", "human_review_outline")
    builder.add_conditional_edges("human_review_outline", route_outline, {
        "generate_draft": "generate_draft",
        # 修复：此前误映射到 generate_outline，人工修改意见从未被真正使用
        "re_generate_outline": "re_generate_outline",
        END: END,
    })
    # re_generate_outline 必须显式回到人工审核，否则节点执行后无出边、流程直接结束
    builder.add_edge("re_generate_outline", "human_review_outline")
    builder.add_edge("generate_draft", "generate_multi_platform")
    builder.add_edge("generate_multi_platform", "auto_check")
    builder.add_edge("auto_check", "human_final_review")
    # 终审 pass/reject 都结束；reject 的稿件会以 review 状态落库
    builder.add_edge("human_final_review", END)
    return builder.compile(checkpointer=get_checkpointer())


def get_graph():
    """编译后的工作流图单例：同一进程只 compile 一次（首次调用时缓存）。"""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH
