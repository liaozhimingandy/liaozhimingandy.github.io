"""文章生成工作流包（从 app/article/llm.py 分层拆出）。

分层结构（业务逻辑、节点函数、ArticleState、提示词与拆分前完全一致）：
    config.py    LLM 连接配置（复用 core.config.Settings）与 HTTP 客户端
    state.py     ArticleState TypedDict + 审核决定常量
    nodes.py     7 个节点函数 + 路由判断 + LLM 调用（提示词外置 prompt/）
    saver.py     Checkpointer 初始化：Postgres 生产 / SQLite 开发 / 内存兜底
    builder.py   StateGraph 装配 + 编译单例（同一进程只 compile 一次）
    runner.py    分段执行入口 run_graph_step / 检查点探测 / resume / CLI
    service.py   GraphService 门面（路由层与独立 worker 的统一调用接口）
    schemas.py   graph 调试接口的 Pydantic 请求契约
    router.py    graph 调试/编排 REST API（SSE 流式 + 快照/状态/图结构）

分层：router.py（调试接口）-> runner/builder/nodes；文章业务接口仍在
../router.py -> ../service.py -> 本包 GraphService（-> runner）；
独立 worker 进程（app/article/worker.py）与 standalone 入口同样通过
GraphService 调用。

⚠️ 解耦约束：workflow 核心与本 __init__ 不得导入 FastAPI/router——
graph/router.py（调试 API）由 main.py 直接从子模块导入挂载，
保证「不装 FastAPI 也能 import 本包运行工作流」。
"""

from . import builder, nodes, runner, saver, state  # noqa: F401
from .builder import get_graph  # noqa: F401
from .service import GraphService, get_graph_service  # noqa: F401
from .config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_RETRIES  # noqa: F401
from .runner import (  # noqa: F401
    initial_state_from_material,
    pending_interrupt,
    resume_command,
    run_graph_step,
    run_one,
    has_checkpoint,
)
from .state import ArticleState, REVIEW_MODIFY, REVIEW_PASS, REVIEW_REJECT  # noqa: F401
