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

from ..core.logger import logger

import argparse
import asyncio
import json
from typing import List, TypedDict

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt  # HITL 审核断点（节点函数内直接调用）

from uuid import uuid7

from ..core.config import get_settings
from . import prompt_manager as prompts

# ========== 1. 配置区 ==========
# LLM 连接参数统一来自 core.config.Settings（.env 自动加载 / 环境变量优先，密钥不入码）；
# 保留模块级常量名，供 service（llm.LLM_MODEL）等既有调用点使用。
_settings = get_settings()
LLM_BASE_URL = _settings.LLM_BASE_URL
LLM_API_KEY = _settings.LLM_API_KEY
LLM_MODEL = _settings.LLM_MODEL
LLM_RETRIES = max(0, int(_settings.LLM_RETRIES))

if not LLM_API_KEY:
    logger.warning("[llm] ⚠️ 未设置 LLM_API_KEY（.env 或环境变量），调用将无法通过鉴权")

# 审核决定的合法取值：通过 / 修改（仅大纲）/ 拒绝
REVIEW_PASS = "pass"
REVIEW_MODIFY = "modify"
REVIEW_REJECT = "reject"


def _parse_review_answer(answer: object) -> tuple[str, str]:
    """把 resume 传入的审核答复解析为 (decision, suggest)。

    结构化来源（前端 API）传 dict：{"decision": "modify", "suggest": "..."}；
    CLI 兼容纯字符串："pass" / "modify" / "reject"。
    任何非法值一律按 reject 处理（fail-closed），避免误放行。
    """
    if isinstance(answer, dict):
        decision = str(answer.get("decision", "")).strip().lower()
        suggest = str(answer.get("suggest", "") or "").strip()
    else:
        decision = str(answer or "").strip().lower()
        suggest = ""
    if decision not in (REVIEW_PASS, REVIEW_MODIFY, REVIEW_REJECT):
        decision = REVIEW_REJECT
    # 终审只允许 pass/reject；modify 在终审阶段无意义，降级为 reject
    return decision, suggest

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
    need_review: bool              # 是否需要人工审核（False：大纲/终审自动通过）
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
                logger.info(f"[llm] 调用失败，重试 {attempt + 1}/{LLM_RETRIES}：{exc}")
    raise last_exc


def generate_outline(state: ArticleState) -> ArticleState:
    """节点1：生成写作大纲"""
    system, user = _get_prompt(_PROMPT_FUNCS["outline"])
    return {"outline": _invoke(system, user.format(**state))}


def human_review_outline(state: ArticleState) -> ArticleState:
    """节点2：人工审核大纲（HITL断点，LangGraph interrupt 暂停）。

    interrupt() 会把 value 原样交给调用方（API/CLI），工作流在此挂起；
    调用方用 Command(resume={"decision":..., "suggest":...}) 恢复时，
    interrupt() 的返回值就是 resume 传入的对象，节点据此产出 state 更新。
    这样审核交互从「服务端 stdin」解耦为「前端/CLI 提交决定」。

    need_review=False（全局配置 ARTICLE_HITL_ENABLED=False 或请求指定）时
    跳过人工审核，大纲自动通过——审核是可配置项而非硬性流程。
    """
    logger.info("=" * 50)
    logger.info("【大纲待审核】")
    logger.info(state["outline"])
    logger.info("=" * 50)
    if not state.get("need_review", True):
        logger.info("人工审核已关闭（need_review=false），大纲自动通过")
        return {"outline_review": REVIEW_PASS, "modify_suggest": ""}
    answer = interrupt({
        "stage": "outline",
        "title": "大纲审核",
        "content": state["outline"],
        "options": ["pass", "modify", "reject"],
    })
    decision, suggest = _parse_review_answer(answer)
    return {"outline_review": decision, "modify_suggest": suggest}


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
    """节点6：人工终审（第二个 HITL 断点，LangGraph interrupt 暂停）。

    need_review=False 时跳过终审，直接以质检后的母稿定稿。
    """
    logger.info("=" * 50)
    logger.info("【自动质检报告】")
    logger.info(state["check_report"])
    logger.info("【母稿】")
    logger.info(state["draft"])
    logger.info("=" * 50)
    if not state.get("need_review", True):
        logger.info("人工审核已关闭（need_review=false），终审自动通过")
        return {"final_review": REVIEW_PASS, "final_article": state["draft"]}
    answer = interrupt({
        "stage": "final",
        "title": "终审",
        "content": json.dumps({
            "check_report": state["check_report"],
            "draft": state["draft"],
            "multi_platform": state.get("multi_platform", {}),
        }, ensure_ascii=False),
        "options": ["pass", "reject"],
    })
    decision, _ = _parse_review_answer(answer)
    # 终审 pass 才定稿；reject 留空 final_article，仍落库供回溯
    final_article = state["draft"] if decision == "pass" else ""
    return {"final_review": decision, "final_article": final_article}


# ========== 3. 编译工作流 ==========
# 检查点（LangGraph 断点续跑）统一存 Postgres（langgraph-checkpoint-postgres），
# 不再使用 SQLite 文件；DSN 来自 Settings（与业务库同一套 AP_DATABASE_URL /
# AP_PG_* 配置）。Postgres 不可达或 DSN 未配置时降级 MemorySaver
# （进程内断点，重启即失，仅影响中断续跑，不影响正常生成）。
# 属运行时内部状态，不进业务库、不参与业务查询。
_CHECKPOINT = None


def _get_checkpointer():
    """惰性构建 checkpointer：优先 Postgres 连接池，不可用降级进程内 MemorySaver。

    用 psycopg_pool 连接池而非单连接：Postgres 重启 / 网络抖动把旧连接
    打断时（psycopg 报 OperationalError: server closed the connection
    unexpectedly），池会在下次取连接时自动重建，长跑数分钟的生成段不会
    因一次连接中断而整体失败。
    """
    global _CHECKPOINT
    if _CHECKPOINT is not None:
        return _CHECKPOINT

    dsn = get_settings().database_dsn
    if dsn:
        try:
            from psycopg_pool import ConnectionPool
            from langgraph.checkpoint.postgres import PostgresSaver

            # autocommit 是 PostgresSaver 的硬要求；
            # prepare_threshold=None 适配 PgBouncer 事务池（与业务库同源约束）
            pool = ConnectionPool(
                dsn,
                min_size=1,
                max_size=4,
                open=True,
                kwargs={"autocommit": True, "prepare_threshold": None},
            )
            checkpointer = PostgresSaver(pool)
            checkpointer.setup()  # 幂等：创建 checkpoint 表
            _CHECKPOINT = checkpointer
            logger.info("[llm] 检查点已连接 Postgres 连接池（psycopg_pool，断线自动重连）")
            return _CHECKPOINT
        except Exception as exc:
            logger.warning(f"[llm] ⚠️ Postgres 检查点不可用，降级内存检查点："
                  f"{type(exc).__name__}: {exc}")
    else:
        logger.warning("[llm] ⚠️ 未配置数据库 DSN，LangGraph 检查点使用进程内内存")

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


def initial_state_from_material(material: dict, need_review: bool = True) -> dict:
    """由素材组装工作流初始 state（服务端分段执行的起点）。

    need_review 控制该次生成是否在大纲/终审断点暂停等人工审核；
    服务层按「请求参数优先，否则读 ARTICLE_HITL_ENABLED 配置」解析后传入。
    """
    state = _build_initial_state(material)
    state["need_review"] = bool(need_review)
    return state


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
    from ..core import database, session_scope
    from .service import ArticleService

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
        # CLI 直接落库（与 service._run_generation 相同的持久化语义）
        status = "done" if state.get("final_review") == "pass" else "review"
        article_id = await ArticleService(session).save_generation_result(
            material, thread_id,
            article_uuid=str(uuid7()),
            state=state, model_name=LLM_MODEL,
        )
    logger.info(f"[llm] 已落库：article={article_id}, event={args.event_id} -> {status}")


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
