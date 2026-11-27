"""从事件池选题并用 LLM 生成文章（LangGraph 工作流）——兼容垫片。

实现已分层拆分到 app/article/graph/ 包（本文件只做再导出，保持
service/tests/CLI 的既有 import 路径不破坏）。迁移映射：

    配置区（LLM_BASE_URL/API_KEY/MODEL/RETRIES、unsafe_http_client）
        -> graph/config.py
    ArticleState、REVIEW_* 常量
        -> graph/state.py
    节点函数（generate_outline / human_review_outline / re_generate_outline /
        generate_draft / generate_multi_platform / auto_check /
        human_final_review）、route_outline、_invoke、_get_llm、
        _parse_review_answer、_PROMPT_FUNCS
        -> graph/nodes.py
    checkpointer（_get_checkpointer）
        -> graph/saver.py（get_checkpointer）
    图装配（_build_graph / get_graph，compile 全局单例）
        -> graph/builder.py
    分段执行（run_graph_step / has_checkpoint / pending_interrupt /
        resume_command / initial_state_from_material / run_one / CLI）
        -> graph/runner.py
    graph 调试/编排接口（SSE stream、state、update-state、checkpoints、
        graph-schema）
        -> graph/router.py（main.py 挂载）

业务逻辑零改动：节点函数、提示词、解析逻辑逐行原样迁移，生成行为一致。
"""

from .graph.config import (  # noqa: F401  兼容旧引用：llm.LLM_MODEL 等
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_RETRIES,
    unsafe_http_client,
)
from .graph.builder import get_graph  # noqa: F401
from .graph.nodes import (  # noqa: F401  兼容旧引用与测试 patch 点
    auto_check,
    generate_draft,
    generate_multi_platform,
    generate_outline,
    human_final_review,
    human_review_outline,
    re_generate_outline,
    route_outline,
)
from .graph.runner import (  # noqa: F401
    has_checkpoint,
    initial_state_from_material,
    pending_interrupt,
    resume_command,
    run_graph_step,
    run_one,
)


def main(argv=None) -> int:
    """CLI 入口：python -m app.article.llm --event-id 2 --auto-approve（委托 runner）。"""
    from .graph.runner import cli

    return cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
