"""从事件池选题并用 LLM 生成文章（LangGraph 工作流）。

模块职责（分层后只做「生成」这一件事，不做任何数据读写）：
    1. 配置区       LLM 连接参数（.env / 环境变量优先，密钥不入码）
    2. 工作流定义   ArticleState、7 个节点、编译后的 graph
                    （提示词外置在 prompt/ 目录，按功能分类，见 prompt_manager.py）
    3. 生成入口     run_one(material, thread_id, auto_approve) -> 最终 state

数据契约：
    - 输入 material 由服务层通过 DAL 的 get_event_material() 组装；
    - 输出最终 state 由服务层通过 DAL 落 article 表并回写 event 状态。
    本模块是同步实现（LangGraph/LangChain 同步 API），由服务层用
    asyncio.to_thread 调入线程执行，不阻塞事件循环。

用法（包模块方式运行）：
    py -3.13 -m app.article.llm --event-id 2 --auto-approve   # 重跑指定事件
"""

import argparse
import asyncio
import json
from typing import List, TypedDict

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from ..core.config import get_settings
from . import prompt_manager as prompts
from .utils import uuid7

# ========== 1. 配置区 ==========
# LLM 连接参数统一来自 core.config.Settings（.env 自动加载 / 环境变量优先，密钥不入码）；
# 保留模块级常量名，供 service（llm.LLM_MODEL）等既有调用点使用。
_settings = get_settings()
LLM_BASE_URL = _settings.LLM_BASE_URL
LLM_API_KEY = _settings.LLM_API_KEY
LLM_MODEL = _settings.LLM_MODEL
LLM_RETRIES = max(0, int(_settings.LLM_RETRIES))

if not LLM_API_KEY:
    print("[llm] ⚠️ 未设置 LLM_API_KEY（.env 或环境变量），调用将无法通过鉴权")

# 非交互模式下自动通过两个人工审核断点；默认保留 HITL
AUTO_APPROVE = False

# verify=False：走本地代理时证书链会变；如需强校验改为 True
unsafe_http_client = httpx.Client(
    verify=False,
    timeout=httpx.Timeout(
        connect=30.0,
        read=None,       # 不限制等待响应数据的时间
        write=60.0,
        pool=30.0,
    ),
)

# LLM 客户端与工作流图均懒加载：import 本模块不触发网络/模型构造，
# 未配置 LLM_API_KEY 时服务照常启动，直到真正调用生成才报清晰错误。
_LLM = None
_GRAPH = None


def _get_llm():
    """按需构造 ChatOpenAI；缺 API Key 时抛出带指引的 RuntimeError。"""
    global _LLM
    if _LLM is None:
        if not LLM_API_KEY:
            raise RuntimeError(
                "LLM_API_KEY 未配置：请在 app/article/.env 或环境变量中设置后重试"
            )
        _LLM = ChatOpenAI(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
            model=LLM_MODEL,
            http_client=unsafe_http_client,
            temperature=0.7,
        )
    return _LLM


# ========== 2. 工作流定义 ==========
# 提示词已外置到 prompt/ 目录，按功能分类（system.md + user.md），
# 见模块顶部说明与 _PROMPT_FUNCS 映射；修改提示词直接编辑 md 文件即可。
class ArticleState(TypedDict):
    event_title: str               # 事件标题（聚合事件输出）
    event_summary: str             # 事件摘要
    source_contents: List[str]     # 已采集的正文素材（来自 news 表）
    source_urls: List[str]         # 溯源链接列表
    outline: str                   # AI 生成大纲
    outline_review: str            # 人工大纲审核结果：pass / reject / modify
    modify_suggest: str            # 人工修改意见
    draft: str                     # 母稿
    multi_platform: dict           # 多平台版本：公众号/百家/头条/小红书/口播/标题组/封面
    check_report: str              # 自动质检报告（幻觉、风险）
    final_review: str              # 人工终审：pass / reject
    final_article: str             # 定稿


_PROMPT_FUNCS = {
    "outline": "outline",               # 生成大纲
    "regen_outline": "outline_revise",  # 按人工意见修订大纲
    "draft": "draft",                   # 生成母稿
    "multi_platform": "multi_platform", # 多平台改编
    "check": "check",                   # 自动质检
}


def _get_prompt(func: str) -> tuple[str, str]:
    """按功能取 (system, user) 提示词，来源 prompt/<func>/{system,user}.md。"""
    return prompts.get_prompt(func, "system"), prompts.get_prompt(func, "user")


def _invoke(system: str, user: str) -> str:
    """统一 LLM 调用入口：system + user 双消息，失败自动重试。"""
    messages = []
    if system:
        messages.append(SystemMessage(content=system))
    if not user:
        raise ValueError("user 提示词为空，无法调用 LLM")
    messages.append(HumanMessage(content=user))
    last_exc = None
    for attempt in range(LLM_RETRIES + 1):
        try:
            return str(_get_llm().invoke(messages).content or "")
        except Exception as exc:
            last_exc = exc
            if attempt < LLM_RETRIES:
                print(f"[llm] 调用失败，重试 {attempt + 1}/{LLM_RETRIES}：{exc}")
    raise last_exc


def generate_outline(state: ArticleState) -> ArticleState:
    """节点1：生成写作大纲"""
    system, user = _get_prompt(_PROMPT_FUNCS["outline"])
    return {"outline": _invoke(system, user.format(**state))}


def human_review_outline(state: ArticleState) -> ArticleState:
    """节点2：人工审核大纲（HITL断点）"""
    print("=" * 50)
    print("【大纲待审核】")
    print(state["outline"])
    print("=" * 50)
    if AUTO_APPROVE:
        print("[auto] 非交互模式，大纲自动通过")
        return {"outline_review": "pass", "modify_suggest": ""}
    review = input("请审核大纲：pass / reject / modify：")
    suggest = ""
    if review == "modify":
        suggest = input("请输入修改意见：")
    return {"outline_review": review, "modify_suggest": suggest}


def route_outline(state: ArticleState):
    """大纲路由判断"""
    if state["outline_review"] == "pass":
        return "generate_draft"
    if state["outline_review"] == "modify":
        return "re_generate_outline"
    return END


def re_generate_outline(state: ArticleState) -> ArticleState:
    """根据人工意见重写大纲"""
    system, user = _get_prompt(_PROMPT_FUNCS["regen_outline"])
    return {
        "outline": _invoke(system, user.format(**state)),
        "outline_review": "",   # 清空，回到人工审核再次确认
        "modify_suggest": "",
    }


def generate_draft(state: ArticleState) -> ArticleState:
    """节点3：生成母稿（主稿）"""
    system, user = _get_prompt(_PROMPT_FUNCS["draft"])
    return {"draft": _invoke(system, user.format(**state))}


def generate_multi_platform(state: ArticleState) -> ArticleState:
    """节点4：基于母稿衍生多平台版本"""
    system, user = _get_prompt(_PROMPT_FUNCS["multi_platform"])
    content = _invoke(system, user.format(**state)).strip()
    # 兼容模型偶尔包裹 ```json ... ```：优先整体解析，失败再截取首个 JSON 对象
    try:
        multi = json.loads(content)
    except (ValueError, TypeError):
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("多平台版本输出不是合法 JSON")
        multi = json.loads(content[start:end + 1])
    if not isinstance(multi, dict):
        raise ValueError("多平台版本输出不是 JSON 对象")
    return {"multi_platform": multi}


def auto_check(state: ArticleState) -> ArticleState:
    """节点5：自动质检：幻觉校验、违规风险检查"""
    system, user = _get_prompt(_PROMPT_FUNCS["check"])
    return {"check_report": _invoke(system, user.format(**state))}


def human_final_review(state: ArticleState) -> ArticleState:
    """节点6：人工终审（第二个HITL断点）"""
    print("=" * 50)
    print("【自动质检报告】")
    print(state["check_report"])
    print("【母稿】")
    print(state["draft"])
    print("=" * 50)
    if AUTO_APPROVE:
        print("[auto] 非交互模式，终审自动通过")
        return {"final_review": "pass", "final_article": state["draft"]}
    review = input("终审：pass / reject：")
    final_article = state["draft"] if review == "pass" else ""
    return {"final_review": review, "final_article": final_article}


# ========== 3. 编译工作流 ==========
# 检查点（LangGraph 断点续跑）统一存 Postgres（langgraph-checkpoint-postgres），
# 不再使用 SQLite 文件；DSN 来自 Settings（与业务库同一套 AP_DATABASE_URL /
# AP_PG_* 配置）。Postgres 不可达或 DSN 未配置时降级 MemorySaver
# （进程内断点，重启即失，仅影响中断续跑，不影响正常生成）。
# 属运行时内部状态，不进业务库、不参与业务查询。
_CHECKPOINT = None


def _get_checkpointer():
    """惰性构建 checkpointer：优先 Postgres，不可用降级进程内 MemorySaver。"""
    global _CHECKPOINT
    if _CHECKPOINT is not None:
        return _CHECKPOINT

    dsn = get_settings().database_dsn
    if dsn:
        try:
            import psycopg
            from langgraph.checkpoint.postgres import PostgresSaver

            # 自管连接：autocommit 是 PostgresSaver 的要求；
            # prepare_threshold=None 适配 PgBouncer 事务池（与业务库同源约束）
            conn = psycopg.Connection.connect(
                dsn, autocommit=True, prepare_threshold=None,
            )
            checkpointer = PostgresSaver(conn)
            checkpointer.setup()  # 幂等：创建 checkpoint 表
            _CHECKPOINT = checkpointer
            print("[llm] 检查点已连接 Postgres（langgraph-checkpoint-postgres）")
            return _CHECKPOINT
        except Exception as exc:
            print(f"[llm] ⚠️ Postgres 检查点不可用，降级内存检查点："
                  f"{type(exc).__name__}: {exc}")
    else:
        print("[llm] ⚠️ 未配置数据库 DSN，LangGraph 检查点使用进程内内存")

    from langgraph.checkpoint.memory import MemorySaver

    _CHECKPOINT = MemorySaver()
    return _CHECKPOINT


def _build_graph():
    """组装并编译工作流图。"""
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
    return builder.compile(checkpointer=_get_checkpointer())


def get_graph():
    """懒加载编译后的工作流图；同一进程只编译一次。"""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


# ========== 4. 生成入口（不含数据读写，落库由服务层负责） ==========
def run_one(material: dict, thread_id: str, auto_approve: bool = True) -> dict:
    """为单个事件跑一次完整工作流，返回最终 state（失败返回空 dict）。

    material：DAL get_event_material() 组装的素材（EventMaterial.model_dump()）；
    thread_id：由调用方按「每次运行」生成，不能只取 event_id，
    否则第二次运行会命中旧 checkpoint，把上次的 outline/draft 带进来污染新输入。
    """
    global AUTO_APPROVE
    AUTO_APPROVE = auto_approve
    event_id = int(material["id"])
    print(f"\n===== 开始流水线：event={event_id} thread={thread_id} "
          f"{material.get('event_title')} =====")
    try:
        final_state = _run_one(material, thread_id)
    except Exception as exc:
        print(f"❌ 事件 {event_id} 生成失败：{type(exc).__name__}: {exc}")
        return {}
    if not final_state:
        return {}
    _print_final(final_state)
    return final_state


def _build_initial_state(pick: dict) -> ArticleState:
    """正文素材来自 DAL get_event_material()，已关联 news 表取好并截断。"""
    return {
        "event_title": pick.get("event_title") or "",
        "event_summary": pick.get("event_summary") or "",
        "source_contents": pick.get("source_contents") or [],
        "source_urls": pick.get("source_urls") or [],
        "outline": "",
        "outline_review": "",
        "modify_suggest": "",
        "draft": "",
        "multi_platform": {},
        "check_report": "",
        "final_review": "",
        "final_article": "",
    }


def _run_one(pick: dict, thread_id: str) -> dict:
    """工作流单次执行体：流式跑完所有节点并聚合最终 state。"""
    config = {"configurable": {"thread_id": thread_id}}
    final_state = _build_initial_state(pick)
    try:
        for chunk in get_graph().stream(final_state, config=config, stream_mode="updates"):
            for node_name, update in chunk.items():
                print(f"\n👉 正在执行节点：【{node_name}】")
                print(f"本次输出字段：{list(update.keys())}")
                final_state.update(update)
                print("-" * 70)
    except Exception as exc:
        print(f"❌ 工作流执行失败：{type(exc).__name__}: {exc}")
        return {}
    return final_state


def _print_final(state: dict):
    """打印最终产出：定稿 + 多平台版本。"""
    print("\n===== 🎉 流水线执行完毕 =====")
    print("【定稿文章 final_article】")
    print(state.get("final_article", ""))
    print("\n📱 多平台版本：")
    print(json.dumps(state.get("multi_platform") or {}, ensure_ascii=False, indent=2))


async def _cli_main(args) -> None:
    """CLI：重跑指定事件。走 SQLModel 自动建表（postgres/内存按环境配置）。"""
    from ..core import database, session_scope
    from .service import ArticleService

    await database.init_db()
    async with session_scope() as session:
        material = await ArticleService(session).get_material(args.event_id)
        if material is None:
            print(f"❌ 指定事件不存在：event={args.event_id}")
            return
        run_id = str(uuid7())
        thread_id = f"event_{material.id}_{run_id}"
        state = run_one(material.model_dump(), thread_id, auto_approve=args.auto_approve)
        if not state:
            return
        # CLI 直接落库（与 service._run_generation 相同的持久化语义）
        status = "done" if state.get("final_review") == "pass" else "review"
        article_id = await ArticleService(session).save_generation_result(
            material, thread_id,
            article_uuid=str(uuid7()),
            state=state, model_name=LLM_MODEL,
        )
    print(f"[llm] 已落库：article={article_id}, event={args.event_id} -> {status}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="重跑指定事件的生成工作流")
    parser.add_argument("--event-id", type=int, required=True,
                        help="要重跑的事件 id（旧文章保留为历史版本）")
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="自动通过大纲审核与终审，适合批量/非交互运行",
    )
    _args = parser.parse_args()
    asyncio.run(_cli_main(_args))
