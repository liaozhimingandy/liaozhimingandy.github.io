"""工作流节点函数：从原 app/article/llm.py 原样迁移，业务逻辑零改动。

节点清单（与 builder.py 的图装配一一对应）：
    generate_outline         生成大纲
    human_review_outline     人工审核大纲（HITL interrupt 断点）
    re_generate_outline      按人工意见重写大纲
    generate_draft           生成母稿
    generate_multi_platform  多平台改写（JSON 输出）
    auto_check               自动质检（幻觉/风险）
    human_final_review       人工终审（第二个 HITL interrupt 断点）

提示词外置在 article/prompt/<func>/{system,user}.md，经 prompt_manager 加载；
LLM 调用统一走 _invoke（失败自动重试）。生成稿件的行为与重构前完全一致。
"""

from ...core.logger import logger

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END
from langgraph.types import interrupt  # HITL 审核断点（节点函数内直接调用）

from .. import prompt_manager as prompts
from .config import (
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_RETRIES, unsafe_http_client,
)
from .state import REVIEW_MODIFY, REVIEW_PASS, REVIEW_REJECT, ArticleState

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


# LLM 客户端懒加载：import 本模块不触发网络/模型构造，
# 未配置 LLM_API_KEY 时服务照常启动，直到真正调用生成才报清晰错误。
_LLM = None


def _get_llm():
    """按需构造 ChatOpenAI；缺 API Key 时抛出带指引的 RuntimeError。"""
    global _LLM
    if _LLM is None:
        if not LLM_API_KEY:
            raise RuntimeError(
                "LLM_API_KEY 未配置：请在 app/article/.env 或环境变量中设置后重试"
            )
        from langchain_openai import ChatOpenAI

        _LLM = ChatOpenAI(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
            model=LLM_MODEL,
            http_client=unsafe_http_client,
            temperature=0.7,
        )
    return _LLM


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


# --------------------------------------------------------------------------- #
# 节点函数（原样迁移）
# --------------------------------------------------------------------------- #

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
